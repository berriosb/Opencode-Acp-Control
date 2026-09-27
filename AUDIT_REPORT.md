# AUDIT REPORT: Opencode ACP Control

**Fecha**: 2026-09-26  
**Auditor**: Senior Unix Systems & Concurrency Engineer  
**Objetivo**: Auditoría técnica exhaustiva de concurrencia, descriptores de archivo (FD), robustez cross-platform, protocolo JSON-RPC, seguridad y cobertura de pruebas.  
**Estado**: Completado y remediado en v0.4.1.

---

## Resumen Ejecutivo y Matriz de Findings

| ID | Severidad | Componente | Descripción | Estado |
|---|---|---|---|---|
| **FINDING-01** | **HIGH** | `helper.sh` | Registro tardío de traps: Aborto durante inicialización dejaba FIFOs huérfanos. | **Fixed (v0.4.1)** |
| **FINDING-02** | **HIGH** | `run.py` | Huérfanos sin escalamiento a `SIGKILL`: `stop` fallaba por timeout y `clean` se bloqueaba. | **Fixed (v0.4.1)** |
| **FINDING-03** | **HIGH** | `helper.sh` | Fuga de `umask 077` al proceso hijo OpenCode: corrompía permisos en workspace. | **Fixed (v0.4.1)** |
| **FINDING-04** | **HIGH** | `helper.sh` | Condición de carrera TOCTOU en `start` concurrente sobre el mismo `--runtime-dir`. | Identified |
| **FINDING-05** | **MEDIUM** | `run.py` | Parser de `/proc/[pid]/stat` asumía nombres sin espacios. | **Fixed (v0.4.1)** |
| **FINDING-06** | **MEDIUM** | `run.py` | `read` no categoriza notificaciones vs responses vs server requests en la salida JSON. | Identified |
| **FINDING-07** | **MEDIUM** | `helper.sh` | Omisión de `set -e` combinada con falta de checks explícitos oculta errores en disco lleno. | Identified |
| **FINDING-08** | **MEDIUM** | `ci.yml` | Ausencia de `shellcheck` en CI. | **Fixed (v0.4.1)** |
| **FINDING-09** | **MEDIUM** | `tests` | Tests no cubrían contención de locks, timeouts de read, EOF abortivo ni flujo bidireccional. | Partial (v0.4.1) |
| **FINDING-10** | **LOW** | `SKILL.md` | El modo "No-Python" no ofrece mecanismo de locking y la regla crítica carece de contraste visual. | Identified |
| **FINDING-11** | **LOW** | `run.py` | `--cwd` no valida contención en sandbox (permite cualquier directorio del sistema). | Identified |

---

## 1. Correctness del FIFO Controller (`helper.sh` + `run.py`)

### 1.1 Permanencia de FD 3 / FD 4 y flujo `fork` + `exec`
* **Veredicto de Descriptores**: CORRECTO.
  - **Evitación de herencia**: La redirección del subshell se evalúa al bifurcar el subproceso antes de que el proceso padre ejecute `exec 3>` y `exec 4<`, por lo que OpenCode no hereda los descriptores 3 ni 4.
  - **Prevención de deadlock en la apertura**:
    - El hijo abre `stdin_fifo` como `O_RDONLY` (bloquea hasta que haya un writer).
    - El padre abre `stdin_fifo` con `exec 3>` (`O_WRONLY`), desbloqueando la lectura del hijo.
    - El hijo procede a abrir `stdout_fifo` como `O_WRONLY` (bloquea hasta que haya un reader).
    - El padre abre `stdout_fifo` con `exec 4<` (`O_RDONLY`), desbloqueando la escritura del hijo.
  - **Permanencia**: El loop `while IFS= read -r frame <&4` lee continuamente del FD 4. El FD 3 permanece abierto en el shell hasta la ejecución del trap `cleanup`.

### 1.2 Race conditions entre `send` (writer efímero) y la persistencia de FD 3
* `run.py send` abre el FIFO con `os.O_WRONLY | os.O_NONBLOCK`. Como OpenCode ya tiene abierto el extremo de lectura, `open` tiene éxito inmediato sin bloquear.
* Al cerrar `send`, el recuento de escritores pasa de 2 a 1 (FD 3 del controller sigue vivo). OpenCode no ve EOF.

### 1.3 File Lock de `send` e Interleaving de Frames
* `run.py` usa `fcntl.flock(lock.fileno(), fcntl.LOCK_EX)` envolviendo `os.open`, `write_nonblocking` y `os.close`. Previene eficazmente el interleaving entre procesos `run.py send` concurrentes.
* En el modo "No-Python", la invocación directa `printf ... > stdin.fifo` no adquiere `send.lock`.

### 1.4 Crash de OpenCode antes de `initialize` y detección Zombie vs Vivo
* En Linux, `proc_stat.read_text().split()[2] == "Z"` fallaba si el ejecutable tenía espacios o paréntesis. Corregido en v0.4.1 usando `rpartition(")")[2].split()[0]`.

### 1.5 OpenCode huérfano si el usuario mata el controller
* Corregido en v0.4.1: `run.py stop` escala a `os.kill(opencode_pid, signal.SIGKILL)` si el proceso no responde a `SIGTERM` tras vencer el deadline.

### 1.6 Dos `start` concurrentes al mismo `--runtime-dir`
* En `run.py`: `mkdir(exist_ok=False)` previene colisiones.
* En `helper.sh`: `mkdir -p` seguido de `[[ ! -e ... ]]` presenta un TOCTOU si dos llamadas concurren simultáneamente.

---

## 2. Robustez Cross-Platform / Cross-Shell

### 2.1 `set -uo pipefail` sin `-e` en `helper.sh`
* Omitido intencionalmente para evitar abortos prematuros en traps y `kill -0`. Sin embargo, comandos de redirección sin checks explícitos pueden ocultar fallos si el disco se llena.

### 2.2 Compatibilidad macOS (BSD) vs Linux
* `mkfifo -m 600`, `ps -p <pid> -o command=` y `sleep 0.05` son compatibles con Linux y macOS.

### 2.3 Fuga de `umask 077` al proceso hijo
* Corregido en v0.4.1: El umask original del llamador se preserva y restaura en el subshell que invoca a OpenCode: `( umask "$orig_umask"; exec ... ) &`.

---

## 3. Protocol Correctness (JSON-RPC 2.0 & ACP v1)

* `run.py send` valida JSON bien formado y clave `"jsonrpc":"2.0"`.
* `run.py read` devuelve una lista plana `frames` sin distinguir notificaciones de respuestas.
* El orden de llegada en stdout se preserva estrictamente.
* La máquina de estados (`initialize` antes de `session/new`) se gobierna en la capa del cliente/agente documentada en `SKILL.md`.

---

## 4. Cobertura de Tests

* `tests/test_transport.py` cubre inicio, creación de FIFOs, persistencia ante múltiples send, modo foreground, parada limpia, rechazo de JSON-RPC inválido, recuperación ante SIGKILL del controller, preservación de umask y escalamiento a SIGKILL ante hijos rebeldes.
