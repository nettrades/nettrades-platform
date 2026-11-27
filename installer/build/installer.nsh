!macro customInstall
    SetOutPath "$INSTDIR\service"
    File "${PROJECT_DIR}/service/nettrades-netsvc.exe"
    File "${PROJECT_DIR}/service/tunnel.dll"
    File "${PROJECT_DIR}/service/wireguard.dll"
    nsExec::ExecToLog '"$INSTDIR\service\nettrades-netsvc.exe" install'
    nsExec::ExecToLog '"$INSTDIR\service\nettrades-netsvc.exe" start'
!macroend

!macro customUnInstall
    nsExec::ExecToLog '"$INSTDIR\service\nettrades-netsvc.exe" stop'
    nsExec::ExecToLog '"$INSTDIR\service\nettrades-netsvc.exe" uninstall'
!macroend