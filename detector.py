"""Node 3 - Laptop: detector (rule-based sensor fusion) + server dashboard."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from nodes.detector_service.main import main

if __name__ == "__main__":
    main()
