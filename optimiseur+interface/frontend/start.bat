@echo off
echo === Lancement de l'interface Vite Maghreb Steel ===

REM Définir le chemin vers Node.js portable
set PATH=C:\Users\benabdellouahad\Downloads;%PATH%

REM Vérifier que Node est bien trouvé
node --version
npm --version

echo.
echo Installation des dépendances (si nécessaire)...
call npm install

echo.
echo Lancement du serveur de développement Vite...
call npm run dev

pause