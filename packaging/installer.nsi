; NSIS 把程序文件、语言资源和 PATH 助手放入同一个离线安装包。
Unicode true
ManifestDPIAware true
!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "x64.nsh"
!include "WinVer.nsh"
!include "Sections.nsh"

!define APP_NAME "DS Context Hub"
!define INSTALLED_APP_ICON "$INSTDIR\_internal\assets\ds-context-hub.ico"
!define APP_KEY "Software\MoonCat-640\DS Context Hub"
!define UNINSTALL_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\DSContextHub"
; Admin 决定 UAC 提权。用户随后选择的安装范围决定 SHCTX 指向 HKCU 还是 HKLM。
!define MULTIUSER_EXECUTIONLEVEL Admin
!define MULTIUSER_MUI
!define MULTIUSER_INSTALLMODE_COMMANDLINE
!define MULTIUSER_USE_PROGRAMFILES64
!define MULTIUSER_INSTALLMODE_INSTDIR "DS Context Hub"
!define MULTIUSER_INSTALLMODE_INSTDIR_REGISTRY_KEY "${APP_KEY}"
!define MULTIUSER_INSTALLMODE_INSTDIR_REGISTRY_VALUENAME "InstallLocation"
!define MULTIUSER_INSTALLMODE_DEFAULT_REGISTRY_KEY "${APP_KEY}"
!define MULTIUSER_INSTALLMODE_DEFAULT_REGISTRY_VALUENAME "InstallLocation"
!include "MultiUser.nsh"

Name "${APP_NAME}"
OutFile "${OUTPUT_DIR}\Setup.exe"
BrandingText "${APP_NAME} ${VERSION}"
SetCompressor /SOLID lzma
SetCompressorDictSize 32
VIProductVersion "${VERSION}.0"
VIAddVersionKey /LANG=1033 "ProductName" "${APP_NAME}"
VIAddVersionKey /LANG=1033 "FileDescription" "DS Context Hub Offline Setup"
VIAddVersionKey /LANG=1033 "FileVersion" "${VERSION}"
VIAddVersionKey /LANG=1033 "LegalCopyright" "Copyright (c) 2026 MoonCat-640"

; 向导、安装器和卸载器共用蓝鲸图标。桌面快捷方式显式引用安装后的同一 ICO。
!define MUI_ICON "${PROJECT_ROOT}\assets\ds-context-hub.ico"
!define MUI_UNICON "${MUI_ICON}"
!define MUI_ABORTWARNING
!define MUI_LANGDLL_ALLLANGUAGES
!define MUI_LANGDLL_REGISTRY_ROOT "SHCTX"
!define MUI_LANGDLL_REGISTRY_KEY "${APP_KEY}"
!define MUI_LANGDLL_REGISTRY_VALUENAME "InstallerLanguage"
; 此处的页面顺序对应用户看到的向导。目录检查同时也在静默安装入口执行。
!insertmacro MUI_RESERVEFILE_LANGDLL
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "${PROJECT_ROOT}\LICENSE"
!insertmacro MULTIUSER_PAGE_INSTALLMODE
!define MUI_PAGE_CUSTOMFUNCTION_LEAVE ValidateDirectory
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_UNPAGE_FINISH
!insertmacro MUI_LANGUAGE "SimpChinese"
!insertmacro MUI_LANGUAGE "English"

LangString CoreSection ${LANG_SIMPCHINESE} "程序文件与开始菜单快捷方式"
LangString CoreSection ${LANG_ENGLISH} "Application and Start menu shortcut"
LangString DesktopSection ${LANG_SIMPCHINESE} "桌面快捷方式"
LangString DesktopSection ${LANG_ENGLISH} "Desktop shortcut"
LangString PathSection ${LANG_SIMPCHINESE} "添加安装目录到 PATH"
LangString PathSection ${LANG_ENGLISH} "Add the installation directory to PATH"
LangString NeedWindows ${LANG_SIMPCHINESE} "需要 Windows 10/11 64 位系统。"
LangString NeedWindows ${LANG_ENGLISH} "Windows 10/11 (64-bit) is required."
LangString InvalidDirectory ${LANG_SIMPCHINESE} "请选择独立的程序文件夹。已有其他安装范围的副本时，请选择另一个目录。"
LangString InvalidDirectory ${LANG_ENGLISH} "Choose a dedicated application folder. Use a different directory for an installation with a different scope."
LangString FolderInUse ${LANG_SIMPCHINESE} "该目录已包含其他文件。请选择空目录或新建一个程序目录。"
LangString FolderInUse ${LANG_ENGLISH} "This folder already contains other files. Choose an empty or new application folder."
LangString ExistingInstall ${LANG_SIMPCHINESE} "该安装范围已有其他目录中的副本。请使用原目录，或先卸载原副本。"
LangString ExistingInstall ${LANG_ENGLISH} "This scope already has a copy in another directory. Use that directory or uninstall the existing copy first."
LangString PathFailure ${LANG_SIMPCHINESE} "无法更新 PATH。程序文件已安装，请检查权限后重试此选项。"
LangString PathFailure ${LANG_ENGLISH} "Unable to update PATH. The application is installed. Check permissions before retrying this option."
LangString RemovePathFailure ${LANG_SIMPCHINESE} "无法清理 PATH，卸载已停止。请关闭程序并重试卸载。"
LangString RemovePathFailure ${LANG_ENGLISH} "Unable to remove the PATH entry. Uninstall has stopped. Close the application and try again."
LangString InvalidUninstall ${LANG_SIMPCHINESE} "安装范围记录缺失或无效，无法安全卸载。请在原目录重新安装后再卸载。"
LangString InvalidUninstall ${LANG_ENGLISH} "The installation scope record is missing or invalid. Reinstall to the same directory before uninstalling."
LangString CloseApplication ${LANG_SIMPCHINESE} "请先关闭正在运行的 DS Context Hub，再重试安装或卸载。"
LangString CloseApplication ${LANG_ENGLISH} "Close DS Context Hub before installing or uninstalling."

Var OriginalUninstallDir
Var InitialDir

Function ValidateDirectory
  ; 首次安装时目录可能尚不存在。Win32 的 GetFullPathNameW 仍可规范化该路径，返回值是字符数。
  Push "$INSTDIR"
  System::Call 'kernel32::GetFullPathNameW(w s, i ${NSIS_MAX_STRLEN}, w .r1, p 0)i.r0'
  ${If} $0 == 0
  ${OrIf} $0 >= ${NSIS_MAX_STRLEN}
    MessageBox MB_OK|MB_ICONSTOP "$(InvalidDirectory)" /SD IDOK
    SetErrorLevel 1
    Abort
  ${EndIf}
  StrCpy $INSTDIR "$1"
  ; 防止把驱动器根目录、系统目录或整个 Program Files 当成本应用的目录。
  ${GetRoot} "$INSTDIR" $0
  ${If} $INSTDIR == $0
  ${OrIf} $INSTDIR == "$0\"
  ${OrIf} $INSTDIR == "$WINDIR"
  ${OrIf} $INSTDIR == "$SYSDIR"
  ${OrIf} $INSTDIR == "$PROGRAMFILES64"
    MessageBox MB_OK|MB_ICONSTOP "$(InvalidDirectory)" /SD IDOK
    SetErrorLevel 1
    Abort
  ${EndIf}
  ReadINIStr $0 "$INSTDIR\install.ini" "Installation" "Mode"
  ; 磁盘标记防止两种范围共用同一目录，注册表位置则用于识别同一范围的重装。
  ${If} $0 != ""
  ${AndIf} $0 != $MultiUser.InstallMode
    MessageBox MB_OK|MB_ICONSTOP "$(InvalidDirectory)" /SD IDOK
    SetErrorLevel 1
    Abort
  ${EndIf}
  ReadRegStr $0 SHCTX "${APP_KEY}" "InstallLocation"
  ${If} $0 != ""
  ${AndIf} $0 != $INSTDIR
    MessageBox MB_OK|MB_ICONSTOP "$(ExistingInstall)" /SD IDOK
    SetErrorLevel 1
    Abort
  ${EndIf}
  ${If} $0 != $INSTDIR
    ; 首次安装只接收新目录或空目录，避免覆盖用户原有的文件。
    FindFirst $0 $1 "$INSTDIR\*"
    ${DoWhile} $1 != ""
      ${If} $1 != "."
      ${AndIf} $1 != ".."
        FindClose $0
        MessageBox MB_OK|MB_ICONSTOP "$(FolderInUse)" /SD IDOK
        SetErrorLevel 1
        Abort
      ${EndIf}
      FindNext $0 $1
    ${Loop}
    ${If} $0 != ""
      FindClose $0
    ${EndIf}
  ${EndIf}
  Call CheckApplicationClosed
  ClearErrors
  SetErrorLevel 0
FunctionEnd

!macro ApplicationClosed PREFIX
Function ${PREFIX}CheckApplicationClosed
  ; 尝试取得 exe 的写入句柄。Windows 正在运行它时会拒绝，安装与卸载都能据此暂停。
  IfFileExists "$INSTDIR\ds_context_hub.exe" 0 done
  ClearErrors
  FileOpen $0 "$INSTDIR\ds_context_hub.exe" a
  ${If} ${Errors}
    MessageBox MB_OK|MB_ICONSTOP "$(CloseApplication)" /SD IDOK
    SetErrorLevel 1
    Abort
  ${EndIf}
  FileClose $0
  done:
FunctionEnd
!macroend
!insertmacro ApplicationClosed ""
!insertmacro ApplicationClosed "un."

Section "$(CoreSection)" Core
  ; 必选组件记录安装范围、注册 Windows 卸载入口，并按构建时生成的清单复制文件。
  SectionIn RO
  Call ValidateDirectory
  SetOutPath "$INSTDIR"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  WriteINIStr "$INSTDIR\install.ini" "Installation" "Mode" "$MultiUser.InstallMode"
  WriteRegStr SHCTX "${APP_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr SHCTX "${APP_KEY}" "InstallMode" "$MultiUser.InstallMode"
  WriteRegStr SHCTX "${APP_KEY}" "InstallerLanguage" "$LANGUAGE"
  WriteRegStr SHCTX "${UNINSTALL_KEY}" "DisplayName" "${APP_NAME}"
  WriteRegStr SHCTX "${UNINSTALL_KEY}" "DisplayVersion" "${VERSION}"
  WriteRegStr SHCTX "${UNINSTALL_KEY}" "Publisher" "MoonCat-640"
  WriteRegStr SHCTX "${UNINSTALL_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr SHCTX "${UNINSTALL_KEY}" "DisplayIcon" "$INSTDIR\ds_context_hub.exe"
  WriteRegStr SHCTX "${UNINSTALL_KEY}" "UninstallString" '$\"$INSTDIR\Uninstall.exe$\" /$MultiUser.InstallMode'
  WriteRegStr SHCTX "${UNINSTALL_KEY}" "QuietUninstallString" '$\"$INSTDIR\Uninstall.exe$\" /$MultiUser.InstallMode /S'
  WriteRegStr SHCTX "${UNINSTALL_KEY}" "URLInfoAbout" "https://github.com/MoonCat-640/DS_Context_Hub"
  WriteRegDWORD SHCTX "${UNINSTALL_KEY}" "NoModify" 1
  WriteRegDWORD SHCTX "${UNINSTALL_KEY}" "NoRepair" 1
  WriteRegDWORD SHCTX "${UNINSTALL_KEY}" "EstimatedSize" ${INSTALLED_KB}
  !include "${GENERATED_DIR}\payload-install.nsh"
  ; 上一条 File 指令可能位于某个子目录。复位后，快捷方式的工作目录就是程序根目录。
  SetOutPath "$INSTDIR"
  CreateDirectory "$SMPROGRAMS\${APP_NAME}"
  CreateShortcut "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" "$INSTDIR\ds_context_hub.exe" "" "${INSTALLED_APP_ICON}" 0
  CreateShortcut "$SMPROGRAMS\${APP_NAME}\Uninstall.lnk" "$INSTDIR\Uninstall.exe" "/$MultiUser.InstallMode"
SectionEnd

Section "$(DesktopSection)" Desktop
  ; 记录此选项，卸载时据此决定是否清理桌面快捷方式。
  CreateShortcut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\ds_context_hub.exe" "" "${INSTALLED_APP_ICON}" 0
  WriteRegDWORD SHCTX "${APP_KEY}" "DesktopShortcut" 1
SectionEnd

!macro ManagePath ACTION
  ; 从安装器自身解出助手并等它完成，成功后广播环境变化，供后续打开的程序使用新值。
  InitPluginsDir
  File "/oname=$PLUGINSDIR\PathEntry.exe" "${GENERATED_DIR}\PathEntry.exe"
  ClearErrors
  ExecWait '"$PLUGINSDIR\PathEntry.exe" ${ACTION} $MultiUser.InstallMode "$INSTDIR"' $0
  ${If} ${Errors}
    StrCpy $0 1
  ${EndIf}
  ${If} $0 == 0
    SendMessage ${HWND_BROADCAST} ${WM_SETTINGCHANGE} 0 "STR:Environment" /TIMEOUT=2000
  ${EndIf}
!macroend

Section /o "$(PathSection)" AddPath
  ; /o 表示默认不选。向导中的复选项和静默安装的 /AddToPath 都会选中此节。
  !insertmacro ManagePath add
  ${If} $0 != 0
    MessageBox MB_OK|MB_ICONEXCLAMATION "$(PathFailure)" /SD IDOK
    SetErrorLevel 2
  ${EndIf}
SectionEnd

Function .onInit
  SetRegView 64
  ; MultiUser 会根据范围计算默认目录，先保存调用者通过 /D= 指定的位置。
  StrCpy $InitialDir "$INSTDIR"
  !insertmacro MULTIUSER_INIT
  ${If} $InitialDir != ""
    StrCpy $INSTDIR "$InitialDir"
  ${EndIf}
  !insertmacro MUI_LANGDLL_DISPLAY
  ${IfNot} ${AtLeastWin10}
  ${OrIfNot} ${RunningX64}
    MessageBox MB_OK|MB_ICONSTOP "$(NeedWindows)" /SD IDOK
    SetErrorLevel 1
    Quit
  ${EndIf}
  ${GetParameters} $0
  ClearErrors
  ${GetOptions} $0 "/AddToPath" $1
  ${IfNot} ${Errors}
    !insertmacro SelectSection ${AddPath}
  ${EndIf}
FunctionEnd

Function un.onInit
  SetRegView 64
  ; 从卸载器所在目录的标记恢复安装范围，再与该范围的注册表路径核对。
  StrCpy $OriginalUninstallDir "$INSTDIR"
  !insertmacro MULTIUSER_UNINIT
  ReadINIStr $0 "$OriginalUninstallDir\install.ini" "Installation" "Mode"
  ${If} $0 == "CurrentUser"
    Call un.MultiUser.InstallMode.CurrentUser
  ${ElseIf} $0 == "AllUsers"
    Call un.MultiUser.InstallMode.AllUsers
  ${Else}
    MessageBox MB_OK|MB_ICONSTOP "$(InvalidUninstall)" /SD IDOK
    SetErrorLevel 1
    Abort
  ${EndIf}
  StrCpy $INSTDIR "$OriginalUninstallDir"
  ReadRegStr $0 SHCTX "${APP_KEY}" "InstallLocation"
  ${If} $0 != $INSTDIR
    MessageBox MB_OK|MB_ICONSTOP "$(InvalidUninstall)" /SD IDOK
    SetErrorLevel 1
    Abort
  ${EndIf}
  !insertmacro MUI_UNGETLANGUAGE
FunctionEnd

Section "Uninstall"
  Call un.CheckApplicationClosed
  ; 先清理安装器曾添加的 PATH。若清理失败，保留注册信息和文件供用户重试。
  ReadRegStr $1 SHCTX "${APP_KEY}" "PathEntry"
  ${If} $1 != ""
    !insertmacro ManagePath remove
    ${If} $0 != 0
      MessageBox MB_OK|MB_ICONSTOP "$(RemovePathFailure)" /SD IDOK
      SetErrorLevel 1
      Abort
    ${EndIf}
  ${EndIf}
  ; 清单逐个删除发行版文件，RMDir 只会移除空目录，用户后来加入的文件可保留。
  !include "${GENERATED_DIR}\payload-uninstall.nsh"
  Delete "$INSTDIR\install.ini"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
  ReadRegStr $0 SHCTX "${APP_KEY}" "InstallLocation"
  ${If} $0 == $INSTDIR
    ReadRegDWORD $1 SHCTX "${APP_KEY}" "DesktopShortcut"
    ${If} $1 == 1
      Delete "$DESKTOP\${APP_NAME}.lnk"
    ${EndIf}
    Delete "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk"
    Delete "$SMPROGRAMS\${APP_NAME}\Uninstall.lnk"
    RMDir "$SMPROGRAMS\${APP_NAME}"
    DeleteRegKey SHCTX "${UNINSTALL_KEY}"
    DeleteRegKey SHCTX "${APP_KEY}"
  ${EndIf}
SectionEnd
