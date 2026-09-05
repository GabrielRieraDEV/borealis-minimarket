; Instalador de Minimarket (punto 5 de la Fase 6) — RNF-11.
;
; Compilar con Inno Setup 6.3 o superior, DESPUES de `pyinstaller minimarket.spec`:
;     ISCC.exe instalador\minimarket.iss
; Queda `instalador\salida\minimarket-instalador.exe`, un unico archivo que el
; cliente ejecuta y no le pregunta nada mas que donde instalar.
;
; La base de datos NO va dentro de Program Files: ahi el usuario no escribe y
; SQLite no la podria abrir. Vive en «Mis documentos\Minimarket», que es lo que
; `minimarket/infra/rutas.py` busca cuando arranca. La carpeta la crea el
; programa; el instalador no la toca, asi que desinstalar no puede llevarse los
; datos por delante.

#define Nombre "Minimarket"
#define Version "1.2.0"
#define Empresa "Borealis Software Solutions"
#define Ejecutable "Minimarket.exe"

[Setup]
AppId={{7C1B4B7E-9F42-4A3E-9A2B-6F0D2E1C8A31}
AppName={#Nombre}
AppVersion={#Version}
AppPublisher={#Empresa}
DefaultDirName={autopf}\{#Nombre}
DefaultGroupName={#Nombre}
DisableProgramGroupPage=yes
OutputDir=salida
OutputBaseFilename=minimarket-instalador
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\recursos\minimarket.ico
UninstallDisplayIcon={app}\{#Ejecutable}
; Program Files necesita permisos de administrador. Es la unica vez que se
; piden: la aplicacion despues corre como usuario comun.
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName={#Nombre}

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "escritorio"; Description: "Crear un acceso directo en el escritorio"; \
    GroupDescription: "Accesos directos:"

[Files]
; Todo lo que dejo PyInstaller en modo onedir.
Source: "..\dist\Minimarket\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\docs\manual-de-usuario.md"; DestDir: "{app}\docs"; Flags: ignoreversion

[Icons]
Name: "{group}\{#Nombre}"; Filename: "{app}\{#Ejecutable}"
Name: "{group}\Manual de usuario"; Filename: "{app}\docs\manual-de-usuario.md"
Name: "{group}\Desinstalar {#Nombre}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#Nombre}"; Filename: "{app}\{#Ejecutable}"; Tasks: escritorio

; Sin seccion [Dirs]. La carpeta de datos la crea `infra/rutas.base_de_datos`
; en el primer arranque, y ahi es donde tiene que crearse: el instalador corre
; elevado y podria armarla en el perfil del administrador en vez del perfil de
; quien despues atiende la caja. Como el instalador no la crea, tampoco la
; borra: desinstalar deja la base y los respaldos donde estan.

[Run]
Filename: "{app}\{#Ejecutable}"; Description: "Abrir {#Nombre} ahora"; \
    Flags: nowait postinstall skipifsilent
