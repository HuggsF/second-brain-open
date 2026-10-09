import time
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from rich.console import Console

from config import settings
from ingestion.sync import SyncEngine

console = Console()

class VaultChangeHandler(FileSystemEventHandler):
    def __init__(self, sync_engine: SyncEngine):
        super().__init__()
        self.sync_engine = sync_engine
        self.last_sync_time = 0
        self.debounce_seconds = 2.0  # Evita disparos múltiplos em edições rápidas

    def on_any_event(self, event):
        if event.is_directory:
            return
        if not event.src_path.endswith(".md"):
            return

        current_time = time.time()
        if current_time - self.last_sync_time > self.debounce_seconds:
            self.last_sync_time = current_time
            console.print(f"[bold cyan]🔄 Mudança detectada no Vault ({Path(event.src_path).name}). Sincronizando...[/bold cyan]")
            try:
                self.sync_engine.sync_vault(verbose=True)
            except Exception as e:
                console.print(f"[bold red]Erro ao sincronizar via watcher:[/bold red] {e}")

def run_watcher():
    """Inicia o daemon de monitoramento contínuo do Vault."""
    sync_engine = SyncEngine()
    # Sincronização inicial ao iniciar
    sync_engine.sync_vault(verbose=True)

    event_handler = VaultChangeHandler(sync_engine)
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
