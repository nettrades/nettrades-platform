#!/bin/bash

# Script para crear symlinks de archivos a Obsidian
# Uso: link-to-obsidian.sh <archivo>

set -e

# Configuración
OBSIDIAN_TARGET="/Users/danielb/Documents/Boveda-Obsidian/Instrucciones MCP"

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Función de ayuda
show_help() {
    echo "Uso: $(basename $0) <archivo>"
    echo ""
    echo "Crea un symlink del archivo especificado en Obsidian."
    echo ""
    echo "Ejemplos:"
    echo "  $(basename $0) README.md"
    echo "  $(basename $0) /ruta/completa/al/archivo.md"
    echo ""
    echo "Destino: $OBSIDIAN_TARGET"
}

# Validar argumentos
if [ $# -eq 0 ]; then
    echo -e "${RED}Error: Debes especificar un archivo${NC}"
    echo ""
    show_help
    exit 1
fi

if [ "$1" == "-h" ] || [ "$1" == "--help" ]; then
    show_help
    exit 0
fi

SOURCE_FILE="$1"

# Validar que el archivo exista
if [ ! -f "$SOURCE_FILE" ]; then
    echo -e "${RED}Error: El archivo '$SOURCE_FILE' no existe${NC}"
    exit 1
fi

# Obtener ruta absoluta del archivo
SOURCE_FILE=$(cd "$(dirname "$SOURCE_FILE")" && pwd)/$(basename "$SOURCE_FILE")

# Validar que el directorio destino exista
if [ ! -d "$OBSIDIAN_TARGET" ]; then
    echo -e "${YELLOW}Advertencia: El directorio destino no existe${NC}"
    echo -e "${YELLOW}Creando: $OBSIDIAN_TARGET${NC}"
    mkdir -p "$OBSIDIAN_TARGET"
fi

# Obtener nombre del archivo
FILENAME=$(basename "$SOURCE_FILE")
LINK_PATH="$OBSIDIAN_TARGET/$FILENAME"

# Verificar si ya existe un link o archivo
if [ -e "$LINK_PATH" ] || [ -L "$LINK_PATH" ]; then
    echo -e "${YELLOW}Advertencia: Ya existe '$FILENAME' en el destino${NC}"

    # Verificar si es un symlink al mismo archivo
    if [ -L "$LINK_PATH" ]; then
        CURRENT_TARGET=$(readlink "$LINK_PATH")
        if [ "$CURRENT_TARGET" == "$SOURCE_FILE" ]; then
            echo -e "${GREEN}✓ El symlink ya apunta al archivo correcto${NC}"
            exit 0
        fi
    fi

    read -p "¿Reemplazar? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Operación cancelada"
        exit 1
    fi
    rm -f "$LINK_PATH"
fi

# Crear el symlink
ln -s "$SOURCE_FILE" "$LINK_PATH"

echo -e "${GREEN}✓ Symlink creado exitosamente${NC}"
echo -e "  Origen:  $SOURCE_FILE"
echo -e "  Destino: $LINK_PATH"
