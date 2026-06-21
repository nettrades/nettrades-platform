# Configuración del Servidor MCP Odoo para Claude Desktop

Este documento explica cómo configurar Claude Desktop para usar este servidor MCP ejecutándose en Docker.

## Requisitos Previos

- Docker Desktop instalado y ejecutándose
- Claude Desktop instalado
- Archivo `.env` configurado con tus credenciales de Odoo

## Paso 1: Construir la Imagen Docker

Primero, construye la imagen Docker del servidor MCP:

```bash
docker build -t odoo-mcp-server .
```

Verifica que la imagen se creó correctamente:

```bash
docker images | grep odoo-mcp-server
```

## Paso 2: Configurar Claude Desktop

### macOS

Edita el archivo de configuración de Claude Desktop:

```bash
vim ~/Library/Application\ Support/Claude/claude_desktop_config.json
```

### Windows

```
%APPDATA%\Claude\claude_desktop_config.json
```

### Linux

```
~/.config/Claude/claude_desktop_config.json
```

## Paso 3: Agregar la Configuración del Servidor MCP

**IMPORTANTE:** No elimines tu configuración existente. Si ya tienes otros servidores MCP configurados (como `MCP_DOCKER` para el catálogo de MCP Toolkit), debes **agregar** el servidor Odoo a la sección existente.

### Si ya tienes configuración existente:

Agrega el servidor `odoo` dentro de la sección `mcpServers` existente:

```json
{
  "mcpServers": {
    "MCP_DOCKER": {
      "command": "docker",
      "args": [
        "mcp",
        "gateway",
        "run"
      ]
    },
    "odoo": {
      "command": "docker",
      "args": [
        "run",
        "--rm",
        "--init",
        "-i",
        "--env-file",
        "/Users/danielb/claude-odoo-api/.env",
        "odoo-mcp-server"
      ]
    }
  },
  "globalShortcut": "Ctrl+Space"
}
```

### Si es tu primera configuración MCP:

```json
{
  "mcpServers": {
    "odoo": {
      "command": "docker",
      "args": [
        "run",
        "--rm",
        "-i",
        "--env-file",
        "/Users/danielb/claude-odoo-api/.env",
        "odoo-mcp-server"
      ]
    }
  }
}
```

**IMPORTANTE:** Reemplaza `/Users/danielb/claude-odoo-api/.env` con la ruta absoluta a tu archivo `.env`.

### Si tu Odoo está en localhost

Si tu instancia de Odoo está ejecutándose en `localhost`, necesitas usar `host.docker.internal` en tu archivo `.env`:

```ini
[company1]
ODOO_URL=http://host.docker.internal:8069
ODOO_DATABASE=database_name
ODOO_API_KEY=api_key_here
```

O puedes usar la red del host:

```json
{
  "mcpServers": {
    "odoo": {
      "command": "docker",
      "args": [
        "run",
        "--rm",
        "-i",
        "--network",
        "host",
        "--env-file",
        "/Users/danielb/claude-odoo-api/.env",
        "odoo-mcp-server"
      ]
    }
  }
}
```

## Paso 4: Reiniciar Claude Desktop

Cierra completamente Claude Desktop y vuelve a abrirlo para que cargue la nueva configuración.

## Verificación

1. Abre Claude Desktop
2. En la interfaz de chat, busca el ícono de herramientas (🔧) o la lista de servidores MCP
3. Deberías ver "odoo" en la lista de servidores conectados
4. Intenta usar una herramienta, por ejemplo:
   - "Lista las empresas configuradas"
   - "Busca los primeros 5 partners en [nombre_empresa]"

## Solución de Problemas

### El servidor no aparece en Claude Desktop

1. Verifica que la imagen Docker existe:
   ```bash
   docker images | grep odoo-mcp-server
   ```

2. Prueba ejecutar el contenedor manualmente:
   ```bash
   docker run --rm -i --env-file .env odoo-mcp-server
   ```

3. Revisa los logs de Claude Desktop (si están disponibles)

### Error de conexión a Odoo

1. Si tu Odoo está en localhost, asegúrate de usar `host.docker.internal` o `--network host`

2. Verifica que las credenciales en `.env` son correctas

3. Prueba la conexión manualmente:
   ```bash
   docker run --rm -i --env-file .env odoo-mcp-server
   ```

### Permisos de archivo

Asegúrate de que el archivo `.env` tiene permisos de lectura:

```bash
chmod 644 .env
```

## Configuración Avanzada

### Usar variables de entorno específicas

Si no quieres usar `--env-file`, puedes pasar las variables individualmente:

```json
{
  "mcpServers": {
    "odoo": {
      "command": "docker",
      "args": [
        "run",
        "--rm",
        "-i",
        "-e", "ODOO_URL=http://host.docker.internal:8069",
        "-e", "ODOO_DATABASE=tu_database",
        "-e", "ODOO_API_KEY=tu_api_key",
        "odoo-mcp-server"
      ]
    }
  }
}
```

### Múltiples configuraciones

Puedes tener múltiples servidores MCP con diferentes configuraciones:

```json
{
  "mcpServers": {
    "odoo-production": {
      "command": "docker",
      "args": [
        "run",
        "--rm",
        "-i",
        "--env-file",
        "/path/to/production/.env",
        "odoo-mcp-server"
      ]
    },
    "odoo-staging": {
      "command": "docker",
      "args": [
        "run",
        "--rm",
        "-i",
        "--env-file",
        "/path/to/staging/.env",
        "odoo-mcp-server"
      ]
    }
  }
}
```

## Notas Importantes

- Claude Desktop iniciará un nuevo contenedor cada vez que comience una conversación
- El flag `--rm` asegura que el contenedor se elimine automáticamente cuando termine
- El flag `-i` es necesario para la comunicación stdio entre Claude Desktop y el servidor MCP
- No uses `docker-compose` para Claude Desktop; usa `docker run` directamente
