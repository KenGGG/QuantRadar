# Third-party dependencies

QuantRadar2 uses the externally installed BulletTrade source at D:/Projects/BulletTrade; the engine is not vendored or modified here. Its version/source identity is recorded in G0/G2 acceptance artifacts. Retain upstream licenses in the external installation.

Frontend dependencies (React, Ant Design, Monaco, Vite and others) remain identified in frontend/package.json and package-lock.json; their license files remain in installed packages. Python application dependencies are declared in pyproject.toml; requirements.lock is the accepted local environment snapshot, including BulletTrade transitive dependencies.

Old DataHub adaptations have been removed; their former notices no longer describe code distributed by this project. Previous files remain recoverable in Git history.
