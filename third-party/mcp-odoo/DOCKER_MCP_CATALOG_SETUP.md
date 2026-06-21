# Configuración de Servidor MCP con Docker MCP Gateway

Esta guía explica cómo configurar un servidor MCP personalizado usando Docker MCP Gateway y catálogos personalizados.

## Tabla de Contenidos

- [Requisitos Previos](#requisitos-previos)
- [Paso 1: Crear el Dockerfile](#paso-1-crear-el-dockerfile)
- [Paso 2: Construir la Imagen Docker](#paso-2-construir-la-imagen-docker)
- [Paso 3: Crear el Catálogo MCP](#paso-3-crear-el-catálogo-mcp)
- [Paso 4: Importar el Catálogo](#paso-4-importar-el-catálogo)
- [Paso 5: Habilitar el Servidor](#paso-5-habilitar-el-servidor)
- [Paso 6: Verificar Configuración](#paso-6-verificar-configuración)
- [Paso 7: Conectar con Claude Desktop](#paso-7-conectar-con-claude-desktop)
- [Troubleshooting](#troubleshooting)

## Requisitos Previos

- Docker Desktop instalado con Docker MCP Gateway
- Servidor MCP funcional (código fuente)
- Cliente MCP compatible (Claude Desktop, Cursor, etc.)

## Paso 1: Crear el Dockerfile

Crea un `Dockerfile` en la raíz de tu proyecto:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Copiar requirements e instalar dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código del servidor MCP
COPY src/ ./src/

# Variables de entorno (opcionales, pueden sobrescribirse)
ENV ODOO_URL=http://localhost:8069
ENV ODOO_DATABASE=""
ENV ODOO_API_KEY=""

# Ejecutar el servidor MCP
CMD ["python", "src/odoo_mcp_server.py"]
```

**Notas importantes:**
- El servidor debe ejecutarse en modo stdio (no HTTP)
- El WORKDIR debe coincidir con las rutas de volúmenes que uses

## Paso 2: Construir la Imagen Docker

Construye la imagen Docker con un tag específico:

```bash
docker build -t nombre-servidor-mcp:latest .
```

**Ejemplo:**
```bash
docker build -t odoo-mcp-server:latest .
```

Verifica que la imagen se creó correctamente:

```bash
docker images | grep nombre-servidor-mcp
```

## Paso 3: Crear el Catálogo MCP

Crea un archivo YAML con el formato de catálogo v3. Ejemplo: `mi-catalogo.yaml`

```yaml
version: 3
name: mi-catalogo-mcp
displayName: Mi Catálogo MCP
description: Catálogo personalizado con servidores MCP

registry:
  nombre-servidor:
    description: Descripción del servidor
    title: Título del Servidor
    type: server
    dateAdded: "2025-11-08T00:00:00Z"
    image: nombre-servidor-mcp:latest
    ref: ""

    # Volúmenes (opcional)
    volumes:
      - "/ruta/local/.env:/app/.env:ro"
      - "/ruta/local/data:/app/data"

    # Variables de entorno (opcional)
    env:
      - name: "VARIABLE_NAME"
        value: "valor"

    # Metadatos (opcional)
    metadata:
      category: business
      tags:
        - etiqueta1
        - etiqueta2
```

**Campos importantes:**

- `version`: Siempre usar `3` para el formato actual
- `name`: Identificador único del catálogo (sin espacios)
- `displayName`: Nombre visible del catálogo
- `registry`: Diccionario de servidores
  - Clave: nombre del servidor (usado para habilitarlo)
  - `image`: Nombre de la imagen Docker (debe coincidir con el tag del Paso 2)
  - `volumes`: Array de montajes en formato `"host:container:opciones"`
  - `env`: Array de variables de entorno
  - `ref`: Dejar vacío `""` para imágenes locales

**Ejemplo completo (Odoo MCP Server):**

```yaml
version: 3
name: bmya-mcp-catalog
displayName: BMyA MCP Catalog
description: Catálogo personalizado con servidores MCP de BMyA

registry:
  odoo-api:
    description: Servidor MCP para Odoo ERP - Soporte Multi-Compañía
    title: Odoo API Server
    type: server
    dateAdded: "2025-11-08T00:00:00Z"
    image: odoo-mcp-server:latest
    ref: ""
    volumes:
      - "/Users/usuario/proyecto/.env:/app/.env:ro"
    metadata:
      category: business
      tags:
        - odoo
        - erp
        - api
```

## Paso 4: Importar el Catálogo

### Opción A: Importar desde archivo local

1. Copia el catálogo al directorio de Docker MCP:

```bash
cp mi-catalogo.yaml ~/.docker/mcp/catalogs/
```

2. Importa el catálogo:

```bash
docker mcp catalog import ~/.docker/mcp/catalogs/mi-catalogo.yaml
```

### Opción B: Reimportar catálogo existente

Si necesitas actualizar un catálogo:

```bash
# Eliminar catálogo anterior
docker mcp catalog rm mi-catalogo-mcp

# Copiar archivo actualizado
cp mi-catalogo.yaml ~/.docker/mcp/catalogs/

# Reimportar
docker mcp catalog import ~/.docker/mcp/catalogs/mi-catalogo.yaml
```

### Verificar catálogo importado

```bash
# Listar todos los catálogos
docker mcp catalog ls

# Ver servidores en el catálogo
docker mcp catalog show mi-catalogo-mcp
```

Deberías ver algo como:

```
MCP Server Directory
  1 servers available
  ────────────────────────────────────────────────────────────────────────────

  nombre-servidor
    Descripción del servidor

  ────────────────────────────────────────────────────────────────────────────
  1 servers total
```

## Paso 5: Habilitar el Servidor

Habilita el servidor para que esté disponible:

```bash
docker mcp server enable nombre-servidor
```

Verifica que esté habilitado:

```bash
docker mcp server ls
```

Deberías ver tu servidor en la lista de servidores habilitados.

## Paso 6: Verificar Configuración

Prueba el gateway para confirmar que todo funciona:

```bash
docker mcp gateway run
```

Busca en la salida líneas como estas que confirman que tu servidor está configurado correctamente:

```
- Those servers are enabled: ..., nombre-servidor, ...
- Running nombre-servidor-mcp:latest with [...-v /ruta/archivo:/app/archivo:ro]
  > nombre-servidor: (X tools)
```

**Presiona `Ctrl+C` para detener el gateway.**

## Paso 7: Conectar con Claude Desktop

### Verificar conexión

```bash
docker mcp client ls --global
```

Deberías ver:

```
● claude-desktop: connected
  MCP_DOCKER: Docker MCP Catalog (gateway server) (stdio)
```

### Si no está conectado

Conéctalo manualmente:

```bash
docker mcp client connect claude-desktop --global
```

### Usar en Claude Desktop

1. Abre Claude Desktop
2. El servidor MCP debería aparecer automáticamente en la lista de herramientas disponibles
3. Puedes verificarlo buscando las herramientas del servidor en el chat

## Troubleshooting

### Error: "MCP server not found: nombre-servidor"

**Causas comunes:**

1. **Typo en el nombre**: Verifica que el nombre en el catálogo coincida exactamente con el usado en el comando
2. **Formato de catálogo incorrecto**: Asegúrate de usar `version: 3` y `registry:` (no `servers:`)
3. **Catálogo no importado**: Ejecuta `docker mcp catalog show nombre-catalogo` para verificar

**Solución:**
```bash
docker mcp catalog rm nombre-catalogo
cp archivo-catalogo.yaml ~/.docker/mcp/catalogs/
docker mcp catalog import ~/.docker/mcp/catalogs/archivo-catalogo.yaml
docker mcp server enable nombre-servidor
```

### Error: "0 servers available" al mostrar catálogo

**Causa:** Formato de catálogo incorrecto o falta `version: 3`

**Solución:** Verifica que tu catálogo tenga esta estructura:

```yaml
version: 3        # IMPORTANTE: debe ser 3
name: nombre
displayName: Nombre
registry:         # Debe ser "registry", NO "servers"
  servidor1:
    description: ...
    title: ...
    type: server   # Debe incluir este campo
    image: ...
```

### Imagen Docker no encontrada

**Error al ejecutar gateway:**
```
Error: image not found: nombre-servidor-mcp:latest
```

**Solución:**
```bash
# Verificar imágenes disponibles
docker images | grep nombre-servidor

# Si no existe, construirla
docker build -t nombre-servidor-mcp:latest .
```

### Volumen no se monta correctamente

**Síntomas:** El servidor no encuentra archivos de configuración

**Verificación:** Al ejecutar `docker mcp gateway run`, busca la línea que ejecuta tu servidor:

```
- Running nombre-servidor-mcp:latest with [...-v /ruta/host:/ruta/container:ro]
```

**Solución:**
1. Verifica que la ruta del host exista y sea absoluta
2. Verifica que la ruta del contenedor coincida con el WORKDIR del Dockerfile
3. Asegúrate de usar `:ro` para solo lectura si el archivo no necesita modificarse

**Ejemplo correcto:**
```yaml
volumes:
  - "/Users/usuario/proyecto/.env:/app/.env:ro"
```

### Gateway se cierra inmediatamente

**Causa:** Puede ser un problema con algún servidor o configuración

**Diagnóstico:**
```bash
docker mcp gateway run 2>&1 | tee gateway-output.log
```

Revisa `gateway-output.log` para ver errores específicos.

### Claude Desktop no muestra las herramientas

**Verificaciones:**

1. Verifica que Claude Desktop esté conectado:
   ```bash
   docker mcp client ls --global
   ```

2. Reinicia Claude Desktop completamente

3. Verifica que el gateway esté corriendo:
   ```bash
   ps aux | grep "docker mcp gateway"
   ```

4. Revisa los logs del gateway para errores

## Comandos Útiles de Referencia

```bash
# Gestión de catálogos
docker mcp catalog ls                                    # Listar catálogos
docker mcp catalog show nombre-catalogo                  # Ver servidores en catálogo
docker mcp catalog import archivo.yaml                   # Importar catálogo
docker mcp catalog rm nombre-catalogo                    # Eliminar catálogo

# Gestión de servidores
docker mcp server ls                                     # Listar servidores habilitados
docker mcp server enable nombre-servidor                 # Habilitar servidor
docker mcp server disable nombre-servidor                # Deshabilitar servidor

# Gestión de clientes
docker mcp client ls --global                           # Listar clientes
docker mcp client connect claude-desktop --global       # Conectar Claude Desktop

# Gateway
docker mcp gateway run                                  # Ejecutar gateway
docker mcp gateway run --port 8080 --transport streaming  # Modo streaming

# Docker
docker images | grep nombre-servidor                    # Ver imágenes
docker build -t nombre:tag .                           # Construir imagen
docker ps | grep mcp                                    # Ver contenedores MCP corriendo
```

## Estructura de Archivos Recomendada

```
proyecto/
├── src/
│   └── mi_servidor_mcp.py          # Código del servidor
├── .env                             # Variables de entorno
├── Dockerfile                       # Definición de imagen
├── requirements.txt                 # Dependencias Python
├── mi-catalogo.yaml                 # Catálogo MCP
└── DOCKER_MCP_CATALOG_SETUP.md     # Esta guía
```

## Referencias

- [Docker MCP Gateway Documentation](https://docs.docker.com/ai/mcp-catalog-and-toolkit/mcp-gateway/)
- [MCP Catalog Documentation](https://docs.docker.com/ai/mcp-catalog-and-toolkit/catalog/)
- [Docker MCP GitHub](https://github.com/docker/mcp-gateway)
- [Build Custom MCP Catalog](https://www.docker.com/blog/build-custom-mcp-catalog/)
