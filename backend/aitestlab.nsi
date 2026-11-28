; AITestLab Windows installer script (NSIS 3.x)
; Packages the PyInstaller onedir output into a per-user setup.exe.

; ---- Basic metadata ----
; Unicode installer: the script contains Chinese shortcut labels (卸载 ...).
; Without this the compiler reads the file in the ANSI codepage and the
; Start-Menu label comes out as mojibake (e.g. "鍗歌浇 AITestLab.lnk").
Unicode true

!define APP_NAME "AITestLab"
!define APP_VERSION "2.3.13"
!define APP_PUBLISHER "AITestLab"
!define APP_EXE "AITestLab.exe"

Name "${APP_NAME}"
OutFile "dist\${APP_NAME}-Setup-v${APP_VERSION}.exe"
InstallDir "$LOCALAPPDATA\Programs\${APP_NAME}"
InstallDirRegKey HKCU "Software\${APP_NAME}" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID lzma

; ---- Interface ----
!include "MUI2.nsh"
!define MUI_ABORTWARNING
!define MUI_ICON "static\aitestlab.ico"
!define MUI_UNICON "static\aitestlab.ico"

!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "SimpChinese"

; ---- Install ----
Section "Install"
  SetOutPath "$INSTDIR"

  ; Close a running copy first: an upgrade would otherwise hit locked files in
  ; _internal (the process holds its own DLLs) and abort halfway, leaving the
  ; install broken. taskkill is best-effort — if the other copy runs elevated
  ; this silently fails and the copy step reports the error itself.
  nsExec::Exec '"$SYSDIR\taskkill.exe" /F /IM ${APP_EXE}'
  Sleep 1200

  ; Drop the previously installed frontend before writing the new one. Bundles
  ; are content-hashed, so a stale assets/ folder next to a fresh index.html is
  ; how an upgrade ends up serving a page that references files it cannot find
  ; (blank screen). Copying over it is not enough — remove it first.
  RMDir /r "$INSTDIR\_internal\static"

  File /r "dist\AITestLab\*.*"

  ; PEAK PCAN-Basic API (bundled driver support): the DLL is also loaded from
  ; _internal\drivers by the app, but expose the official DLL, EULA and
  ; README at the install root so field engineers can find / copy them.
  SetOutPath "$INSTDIR\drivers"
  File /r "drivers\*.*"
  SetOutPath "$INSTDIR"

  ; Start Menu + Desktop shortcuts
  CreateDirectory "$SMPROGRAMS\${APP_NAME}"
  CreateShortcut "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}"
  CreateShortcut "$SMPROGRAMS\${APP_NAME}\卸载 ${APP_NAME}.lnk" "$INSTDIR\Uninstall.exe"
  CreateShortcut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}"

  WriteUninstaller "$INSTDIR\Uninstall.exe"

  ; Uninstall registry entry (per-user)
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" \
    "DisplayName" "${APP_NAME}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" \
    "DisplayVersion" "${APP_VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" \
    "Publisher" "${APP_PUBLISHER}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" \
    "UninstallString" "$\"$INSTDIR\Uninstall.exe$\""
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" \
    "DisplayIcon" "$INSTDIR\${APP_EXE}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" \
    "InstallLocation" "$INSTDIR"
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" \
    "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" \
    "NoRepair" 1
  WriteRegStr HKCU "Software\${APP_NAME}" "InstallDir" "$INSTDIR"
SectionEnd

; ---- Uninstall ----
Section "Uninstall"
  Delete "$DESKTOP\${APP_NAME}.lnk"
  Delete "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk"
  Delete "$SMPROGRAMS\${APP_NAME}\卸载 ${APP_NAME}.lnk"
  RMDir "$SMPROGRAMS\${APP_NAME}"

  RMDir /r "$INSTDIR"

  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}"
  DeleteRegKey HKCU "Software\${APP_NAME}"
SectionEnd
