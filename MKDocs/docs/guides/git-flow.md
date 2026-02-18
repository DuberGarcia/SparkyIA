# flujo de git

Git Flow es una metodología de ramificación para Git, creada por Vincent Driessen. Proporciona un modelo robusto para gestionar el desarrollo de software mediante el uso de ramas específicas para diferentes propósitos. A continuación, se describen las principales ramas y su propósito:

- **Rama `main`**: Esta es la rama principal que contiene el código de producción. Cada commit en esta rama debe ser una versión estable y lista para ser desplegada.

- **Rama `develop`**: Esta rama sirve como la rama de integración para las características en desarrollo. Aquí es donde se combinan todas las nuevas funcionalidades antes de ser fusionadas en `main` para una nueva versión.

- **Ramas de características (`feature/`)**: Estas ramas se crean a partir de `develop` para trabajar en nuevas funcionalidades. Una vez que la característica está completa, la rama se fusiona de nuevo en `develop`.

- **Rama test ('test/')**: Estas ramas se crean a partir de `develop` para realizar pruebas exhaustivas antes de preparar una nueva versión. Una vez que las pruebas son satisfactorias, la rama se fusiona de nuevo en `develop`.