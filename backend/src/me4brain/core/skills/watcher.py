"""Skill Watcher - File system watcher per hot-reload skill senza restart."""

import asyncio
import contextlib
from collections.abc import Callable
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

# Tentativo di import watchdog, fallback a polling se non disponibile
try:
    from watchdog.events import FileSystemEvent, FileSystemEventHandler
    from watchdog.observers import Observer

    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    logger.warning("watchdog_not_available", message="Fallback a polling mode")


class SkillFileHandler(FileSystemEventHandler if WATCHDOG_AVAILABLE else object):
    """Handler per eventi file system nelle directory skill."""

    def __init__(
        self,
        on_created: Callable[[Path], None] | None = None,
        on_modified: Callable[[Path], None] | None = None,
        on_deleted: Callable[[Path], None] | None = None,
    ):
        self.on_created = on_created
        self.on_modified = on_modified
        self.on_deleted = on_deleted

    def _is_skill_file(self, path: str) -> bool:
        """Verifica se il file è un SKILL.md."""
        return path.endswith("SKILL.md")

    def on_created(self, event: "FileSystemEvent") -> None:
        """Chiamato quando un file viene creato."""
        if event.is_directory:
            return
        if self._is_skill_file(event.src_path):
            logger.info("skill_file_created", path=event.src_path)
            if self.on_created:
                self.on_created(Path(event.src_path))

    def on_modified(self, event: "FileSystemEvent") -> None:
        """Chiamato quando un file viene modificato."""
        if event.is_directory:
            return
        if self._is_skill_file(event.src_path):
            logger.info("skill_file_modified", path=event.src_path)
            if self.on_modified:
                self.on_modified(Path(event.src_path))

    def on_deleted(self, event: "FileSystemEvent") -> None:
        """Chiamato quando un file viene eliminato."""
        if event.is_directory:
            return
        if self._is_skill_file(event.src_path):
            logger.info("skill_file_deleted", path=event.src_path)
            if self.on_deleted:
                self.on_deleted(Path(event.src_path))


class SkillWatcher:
    """
    Monitora directory skill per cambiamenti.

    Supporta due modalità:
    - Watchdog (preferita): notifiche in tempo reale
    - Polling (fallback): controllo periodico ogni N secondi
    """

    def __init__(
        self,
        skill_dir: Path,
        on_change: Callable[[Path, str], None],
        poll_interval: float = 5.0,
    ):
        """
        Inizializza il watcher.

        Args:
            skill_dir: Directory da monitorare
            on_change: Callback chiamata su cambiamenti (path, event_type)
            poll_interval: Intervallo polling in secondi (fallback)
        """
        self.skill_dir = skill_dir
        self.on_change = on_change
        self.poll_interval = poll_interval
        self._running = False
        self._observer: Observer | None = None
        self._poll_task: asyncio.Task | None = None
        self._file_mtimes: dict[Path, float] = {}

    async def start(self) -> None:
        """Avvia monitoring asincrono."""
        if self._running:
            logger.warning("skill_watcher_already_running")
            return

        self._running = True

        # Assicura che la directory esista
        self.skill_dir.mkdir(parents=True, exist_ok=True)

        if WATCHDOG_AVAILABLE:
            await self._start_watchdog()
        else:
            await self._start_polling()

        logger.info(
            "skill_watcher_started",
            directory=str(self.skill_dir),
            mode="watchdog" if WATCHDOG_AVAILABLE else "polling",
        )

    async def _start_watchdog(self) -> None:
        """Avvia watcher con watchdog."""
        handler = SkillFileHandler(
            on_created=lambda p: self.on_change(p, "created"),
            on_modified=lambda p: self.on_change(p, "modified"),
            on_deleted=lambda p: self.on_change(p, "deleted"),
        )
        self._observer = Observer()
        self._observer.schedule(handler, str(self.skill_dir), recursive=True)
        self._observer.start()

    async def _start_polling(self) -> None:
        """Avvia watcher in modalità polling."""
        # Inizializza mtime cache
        self._file_mtimes = self._scan_mtimes()
        self._poll_task = asyncio.create_task(self._poll_loop())

    def _scan_mtimes(self) -> dict[Path, float]:
        """Scansiona tutti i file SKILL.md e registra mtime."""
        mtimes: dict[Path, float] = {}
        for skill_file in self.skill_dir.rglob("SKILL.md"):
            with contextlib.suppress(OSError):
                mtimes[skill_file] = skill_file.stat().st_mtime
        return mtimes

    async def _poll_loop(self) -> None:
        """Loop di polling per rilevare cambiamenti."""
        while self._running:
            try:
                await asyncio.sleep(self.poll_interval)
                current_mtimes = self._scan_mtimes()

                # Rileva nuovi file
                for path in current_mtimes:
                    if path not in self._file_mtimes:
                        self.on_change(path, "created")

                # Rileva file modificati
                for path, mtime in current_mtimes.items():
                    if path in self._file_mtimes and mtime > self._file_mtimes[path]:
                        self.on_change(path, "modified")

                # Rileva file eliminati
                for path in self._file_mtimes:
                    if path not in current_mtimes:
                        self.on_change(path, "deleted")

                self._file_mtimes = current_mtimes

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("skill_watcher_poll_error", error=str(e))

    def stop(self) -> None:
        """Ferma monitoring."""
        self._running = False

        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None

        if self._poll_task:
            self._poll_task.cancel()
            self._poll_task = None

        logger.info("skill_watcher_stopped")

    @property
    def is_running(self) -> bool:
        """Verifica se il watcher è attivo."""
        return self._running
