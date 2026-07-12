"""Perzforge worker agent — runs on the GPU node.

Poll loop skeleton; story B1/B3 implement the real thing:
  1. BRPOP job id from Redis queue
  2. Load job spec from Postgres, mark RUNNING
  3. Launch Docker container (list args, non-root, cap-drop ALL, limits; --gpus if requested)
  4. Stream container logs to Redis pub/sub channel jobs:{id}:logs
  5. On exit: upload artifacts (Phase 2), mark SUCCEEDED/FAILED, loop
"""
import time


def main() -> None:
    print("perzforge-worker: skeleton alive; implement in story B1/B3")
    while True:
        time.sleep(5)


if __name__ == "__main__":
    main()
