from pathlib import Path
import logging


def configure_logging(path: Path = Path('gamecat.log')) -> None:
    """Configure application logging to UTF-8 file and stderr."""
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for handler in list(root.handlers):
        root.removeHandler(handler)
        try: handler.close()
        except Exception: pass
    formatter = logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s')
    file_handler = logging.FileHandler(path, encoding='utf-8')
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)
    stream = logging.StreamHandler(); stream.setFormatter(formatter); root.addHandler(stream)
