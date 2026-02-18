# Usa una imagen base con Python (necesaria para MkDocs)
FROM python:3.11-slim

# Crea un usuario no-root
RUN useradd -m -u 1000 mkdocs

# Define un directorio de trabajo
WORKDIR /app

# Instala MkDocs
# Usa el marcador --no-cache-dir para reducir el tamaño de la imagen
RUN pip install --no-cache-dir mkdocs mkdocs-material

# Cambia el propietario del directorio de trabajo
RUN chown -R mkdocs:mkdocs /app

# Cambia al usuario no-root
USER mkdocs

# Copia los archivos de configuración y la documentación
# El archivo mkdocs.yml debe estar en la raíz de WORKDIR (/app)
# La carpeta docs/ debe estar en la raíz de WORKDIR (/app)
COPY mkdocs.yml mkdocs.yml
COPY docs/ docs/

# Expón el puerto que usa MkDocs para servir la documentación (por defecto es 8000)
EXPOSE 8000

# Comando por defecto para servir la documentación
# El parámetro -a 0.0.0.0 es crucial para que sea accesible desde fuera del contenedor
CMD ["mkdocs", "serve", "-a", "0.0.0.0:8000"]