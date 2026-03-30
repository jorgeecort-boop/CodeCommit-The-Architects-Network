#!/usr/bin/env bash
set -euo pipefail

# Uso:
#   bash scripts/backup_db.sh
#   BACKUP_DIR=/ruta/segura bash scripts/backup_db.sh

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="${ROOT_DIR}/data"
DB_FILE="${DATA_DIR}/codecommit.db"
MEDIA_DIR="${DATA_DIR}/media"

DEFAULT_BACKUP_BASE="${HOME}/codecommit_backups"
BACKUP_BASE="${BACKUP_DIR:-$DEFAULT_BACKUP_BASE}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
TARGET_DIR="${BACKUP_BASE}/backup_${TIMESTAMP}"

mkdir -p "${TARGET_DIR}"

if [[ -f "${DB_FILE}" ]]; then
  cp "${DB_FILE}" "${TARGET_DIR}/codecommit.db"
else
  echo "Aviso: no se encontro ${DB_FILE}"
fi

if [[ -d "${MEDIA_DIR}" ]]; then
  cp -R "${MEDIA_DIR}" "${TARGET_DIR}/media"
else
  echo "Aviso: no se encontro ${MEDIA_DIR}"
fi

cat > "${TARGET_DIR}/README_BACKUP.txt" <<EOF
Backup de CodeCommit generado en: ${TIMESTAMP}
Origen DB: ${DB_FILE}
Origen media: ${MEDIA_DIR}
EOF

echo "Backup completado en: ${TARGET_DIR}"
