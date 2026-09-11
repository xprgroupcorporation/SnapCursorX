!include "MUI.nsh"
!include "x64.nsh"

!define MUI_ICON "Assets/app_icon.ico"
!define BUILD_ROOT "__EXE_Build_Output"
!define INSTALLER_ROOT "__Installer_Output"
!searchparse /file "Data\Config\Info.json" '"VERSION": "' APP_VERSION_RAW '",'
!searchparse /file "Data\Config\Info.json" '"NAME": "' APP_NAME_RAW '",'
!define MUI_WELCOMEPAGE_TITLE "Welcome to the SnapCursorX Setup Wizard"
!define MUI_WELCOMEPAGE_TITLE_3LINES
!define MUI_WELCOMEPAGE_TEXT \
	"This wizard will guide you through the installation process.\r\n\r\nIt is recommended to close any other running SnapCursorX instances before continuing.\r\n\r\nYou do not need to restart your PC after installation. \r\n\r\nBuild Info: ${APP_VERSION_RAW}"

!system 'if not exist "${INSTALLER_ROOT}" mkdir "${INSTALLER_ROOT}"'

RequestExecutionLevel admin

Name "${APP_NAME_RAW}"
InstallDir "$PROGRAMFILES64\SnapCursorX"
InstallDirRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\SnapCursorX" "InstallLocation"
OutFile "${INSTALLER_ROOT}\SnapCursorX_SE_x64_Installer.exe"

BrandingText "XPR Group Corporation"

; Add version information to installer
VIProductVersion "1.0.0.0"
VIAddVersionKey "ProductName" "SnapCursorX"
VIAddVersionKey "CompanyName" "XPR Group Corporation"
VIAddVersionKey "FileVersion" "${APP_VERSION_RAW}"
VIAddVersionKey "ProductVersion" "${APP_VERSION_RAW}"
VIAddVersionKey "FileDescription" "SnapCursorX Installer"
VIAddVersionKey "LegalCopyright" "XPR Group Corporation"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "${BUILD_ROOT}\LICENSE.txt"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN "$INSTDIR\SnapCursorX_SE.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Launch SnapCursorX"
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_WELCOME
!insertmacro MUI_UNPAGE_DIRECTORY
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_UNPAGE_FINISH

!insertmacro MUI_LANGUAGE "English"

Section "Install" section_index_output
	${If} ${RunningX64}
		SetRegView 64
	${EndIf}

	SetOutPath "$INSTDIR"
	WriteUninstaller "$INSTDIR\uninstall.exe"

	WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\SnapCursorX" "DisplayName" "SnapCursorX"
	WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\SnapCursorX" "DisplayVersion" \
		"${APP_VERSION_RAW}"
	WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\SnapCursorX" "Publisher" "XPR Group Corporation"
	WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\SnapCursorX" "DisplayIcon" \
		"$INSTDIR\SnapCursorX_SE.exe"
	WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\SnapCursorX" "InstallLocation" "$INSTDIR"
	WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\SnapCursorX" "NoModify" 1
	WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\SnapCursorX" "NoRepair" 1
	WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\SnapCursorX" "UninstallString" \
		"$INSTDIR\uninstall.exe"

	CreateDirectory "$SMPROGRAMS\SnapCursorX"
	CreateShortcut "$DESKTOP\SnapCursorX.lnk" "$INSTDIR\SnapCursorX_SE.exe" "" "$INSTDIR\SnapCursorX_SE.exe" 0 \
		SW_SHOWNORMAL "" "" "$INSTDIR"
	CreateShortcut "$SMPROGRAMS\SnapCursorX\SnapCursorX.lnk" "$INSTDIR\SnapCursorX_SE.exe" "" \
		"$INSTDIR\SnapCursorX_SE.exe" 0 SW_SHOWNORMAL "" "" "$INSTDIR"
	CreateShortcut "$SMPROGRAMS\SnapCursorX\Uninstall.lnk" "$INSTDIR\uninstall.exe"

	SetOutPath "$INSTDIR"
	File "${BUILD_ROOT}\SnapCursorX_SE.exe"
	File "${BUILD_ROOT}\LICENSE.txt"
	File "${BUILD_ROOT}\README.md"
	File "${BUILD_ROOT}\requirements.txt"

	RMDir /r "$INSTDIR\_internal"
	SetOutPath "$INSTDIR\_internal"
	File /r "${BUILD_ROOT}\_internal\*"

	SetOutPath "$INSTDIR\Data"
	File /r /x "Setups\*" "${BUILD_ROOT}\Data\*"

	IfSilent 0 +3
	Sleep 1000
	ExecShell "open" "$INSTDIR\SnapCursorX_SE.exe"
SectionEnd

Section "Uninstall" section_index_uninstall
	${If} ${RunningX64}
		SetRegView 64
	${EndIf}

	DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\SnapCursorX"

	Delete "$DESKTOP\SnapCursorX.lnk"
	Delete "$SMPROGRAMS\SnapCursorX\SnapCursorX.lnk"
	Delete "$SMPROGRAMS\SnapCursorX\Uninstall.lnk"
	RMDir "$SMPROGRAMS\SnapCursorX"

	RMDir /r "$INSTDIR\_internal"
	RMDir /r "$INSTDIR\Data"

	Delete "$INSTDIR\LICENSE.txt"
	Delete "$INSTDIR\README.md"
	Delete "$INSTDIR\requirements.txt"
	Delete "$INSTDIR\SnapCursorX_SE.exe"
	Delete "$INSTDIR\uninstall.exe"

	RMDir "$INSTDIR"
SectionEnd
