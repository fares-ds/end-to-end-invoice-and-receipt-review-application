set -euo pipefail
cd "$(dirname "$0")/.."

(
  cd backend
  uv run --locked --no-sync uvicorn app.main:create_app --factory --reload
) &
(
  cd frontend
  pnpm dev
) &

trap 'kill 0' EXIT INT TERM
wait
