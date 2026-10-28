import threading
import time
from pathlib import Path
from typing import Callable

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from rich.console import Console

from config import settings
from core.sync_lock import SyncBusy
from ingestion.sync import SyncEngine

console = Console()

class VaultChangeHandler(FileSystemEventHandler):
    """Debounce de borda final: sincroniza uma vez, depois do ultimo evento .md da rajada."""

    def __init__(
        self,
        sync_fn: Callable[[], object],
        debounce_seconds: float = 2.0,
        timer_factory: Callable[[float, Callable], object] = threading.Timer,
    ):
        super().__init__()
        self.sync_fn = sync_fn
        self.debounce_seconds = debounce_seconds
        self.timer_factory = timer_factory
        self._timer = None
        self._lock = threading.Lock()

    def _arm(self):
        """Cancela o timer pendente e arma outro."""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            timer = self.timer_factory(self.debounce_seconds, self._run_sync)
            timer.daemon = True
            self._timer = timer
            timer.start()

    def _run_sync(self):
        try:
            self.sync_fn()
        except SyncBusy:
            console.print("[yellow]Sync ocupado (outro processo segura o lock). Rearmando o timer.[/yellow]")
            self._arm()
        except Exception as e:
            console.print(f"[bold red]Erro ao sincronizar via watcher:[/bold red] {e}")

    def on_any_event(self, event):
        if event.is_directory:
            return
        if not event.src_path.endswith(".md"):
            return

        console.print(f"[bold cyan]🔄 Mudança detectada no Vault ({Path(event.src_path).name}). Sincronizando após {self.debounce_seconds:g}s sem novas edições...[/bold cyan]")
        self._arm()

def run_watcher(timer_factory: Callable[[float, Callable], object] = threading.Timer):
    """Inicia o daemon de monitoramento contínuo do Vault."""
    engine = SyncEngine(lock_wait=30.0)
    event_handler = VaultChangeHandler(lambda: engine.sync_vault(verbose=True), timer_factory=timer_factory)

    # Sincronização inicial ao iniciar. Lock ocupado por outro sync (ex.: --rebuild) depois da
    # espera de 30 s: o watcher não cai, arma o debounce e tenta de novo (spec 6.1, ADR-033 D2).
    try:
        event_handler.sync_fn()
    except SyncBusy:
        console.print("[yellow]Sync inicial ocupado (outro processo segura o lock). Nova tentativa pelo timer.[/yellow]")
        event_handler._arm()

    observer = Observer()
    observer.schedule(event_handler, path=str(settings.vault_dir), recursive=True)
    observer.start()

    console.print(f"[bold green]👀 Observando alterações em {settings.vault_dir}... Pressione Ctrl+C para parar.[/bold green]")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

if __name__ == "__main__":
    run_watcher()
