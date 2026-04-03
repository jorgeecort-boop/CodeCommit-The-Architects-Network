#!/bin/bash
# CodeCommit Backup Script
# Configurar en crontab: crontab -e
# 0 2 * * * /root/codecomit/backup.sh

set -e

BACKUP_DIR="/root/codecomit/backups"
DB_PATH="/app/data/codecommit.db"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="codecommit_$DATE.sql.gz"

mkdir -p "$BACKUP_DIR"

echo "[BACKUP] Starting backup..."

if [ -f "$DB_PATH" ]; then
    # Create gzip compressed SQL dump
    sqlite3 "$DB_PATH" .dump | gzip > "$BACKUP_DIR/$BACKUP_NAME"
    
    # Keep only last 7 backups
    ls -t "$BACKUP_DIR"/codecommit_*.sql.gz | tail -n +8 | xargs -r rm
    
    echo "[BACKUP] Backup created: $BACKUP_NAME"
    echo "[BACKUP] Total backups: $(ls -1 $BACKUP_DIR/*.sql.gz | wc -l)"
else
    echo "[BACKUP] ERROR: Database not found at $DB_PATH"
    exit 1
fi

echo "[BACKUP] Done!"
