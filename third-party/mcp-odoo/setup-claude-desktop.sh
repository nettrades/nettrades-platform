#!/bin/bash

# Script para configurar el servidor MCP Odoo en Claude Desktop

set -e

echo "========================================="
echo "Configuración del Servidor MCP Odoo"
echo "para Claude Desktop con Docker"
echo "========================================="
echo ""

# Verificar que Docker está ejecutándose
if ! docker info > /dev/null 2>&1; then
    echo "❌ Error: Docker no está ejecutándose"
    echo "Por favor, inicia Docker Desktop y vuelve a ejecutar este script"
    exit 1
fi

echo "✅ Docker está ejecutándose"
echo ""

# Construir la imagen Docker
echo "📦 Construyendo la imagen Docker..."
docker build -t odoo-mcp-server .

if [ $? -eq 0 ]; then
    echo "✅ Imagen Docker construida exitosamente"
else
    echo "❌ Error al construir la imagen Docker"
    exit 1
fi

echo ""

# Verificar que existe el archivo .env
if [ ! -f ".env" ]; then
    echo "⚠️  Advertencia: No se encontró el archivo .env"
    echo "Crea un archivo .env con la configuración de tu(s) empresa(s) Odoo"
    echo ""
    echo "Ejemplo:"
    echo "[company1]"
    echo "ODOO_URL=http://host.docker.internal:8069"
    echo "ODOO_DATABASE=tu_database"
    echo "ODOO_API_KEY=tu_api_key"
    echo ""
fi

# Obtener la ruta absoluta del directorio actual
CURRENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$CURRENT_DIR/.env"

# Determinar el sistema operativo
OS_TYPE="$(uname -s)"
case "$OS_TYPE" in
    Darwin*)
        CONFIG_FILE="$HOME/Library/Application Support/Claude/claude_desktop_config.json"
        ;;
    Linux*)
        CONFIG_FILE="$HOME/.config/Claude/claude_desktop_config.json"
        ;;
    MINGW*|MSYS*|CYGWIN*)
        CONFIG_FILE="$APPDATA/Claude/claude_desktop_config.json"
        ;;
    *)
        echo "⚠️  Sistema operativo no reconocido: $OS_TYPE"
        CONFIG_FILE=""
        ;;
esac

echo ""
echo "========================================="
echo "Configuración de Claude Desktop"
echo "========================================="
echo ""

if [ -n "$CONFIG_FILE" ]; then
    echo "📝 Archivo de configuración de Claude Desktop:"
    echo "   $CONFIG_FILE"
    echo ""
    echo "⚠️  IMPORTANTE: Si ya tienes configuración existente (como MCP_DOCKER),"
    echo "   NO la elimines. Agrega el servidor 'odoo' a la sección 'mcpServers' existente."
    echo ""
    echo "Si YA tienes otros servidores MCP configurados, agrega solo esta sección:"
    echo ""
    cat <<EOF
    "odoo": {
      "command": "docker",
      "args": [
        "run",
        "--rm",
        "-i",
        "--env-file",
        "$ENV_FILE",
        "odoo-mcp-server"
      ]
    }
EOF
    echo ""
    echo "Ejemplo con configuración existente:"
    echo ""
    cat <<EOF
{
  "mcpServers": {
    "MCP_DOCKER": {
      "command": "docker",
      "args": ["mcp", "gateway", "run"]
    },
    "odoo": {
      "command": "docker",
      "args": [
        "run",
        "--rm",
        "-i",
        "--env-file",
        "$ENV_FILE",
        "odoo-mcp-server"
      ]
    }
  },
  "globalShortcut": "Ctrl+Space"
}
EOF
    echo ""
    echo "Si tu Odoo está en localhost, agrega '--network' y 'host' a los args:"
    echo ""
    cat <<EOF
    "odoo": {
      "command": "docker",
      "args": [
        "run",
        "--rm",
        "-i",
        "--network",
        "host",
        "--env-file",
        "$ENV_FILE",
        "odoo-mcp-server"
      ]
    }
EOF
fi

echo ""
echo "========================================="
echo "Próximos Pasos"
echo "========================================="
echo ""
echo "1. Asegúrate de que el archivo .env esté configurado correctamente"
echo "2. Agrega la configuración al archivo de Claude Desktop"
echo "3. Reinicia Claude Desktop completamente"
echo "4. Verifica que el servidor MCP aparezca en Claude Desktop"
echo ""
echo "Para más detalles, consulta: CLAUDE_DESKTOP_SETUP.md"
echo ""
echo "✅ Configuración completada"
