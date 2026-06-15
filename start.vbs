Set shell = CreateObject("WScript.Shell")
Set fso   = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)
py   = root & "\.venv\Scripts\python.exe"
tmp  = fso.GetSpecialFolder(2)

' ── Write temp BAT for each service ─────────────────────────────────────────
Sub WriteBat(path, title, dir, cmd)
    Set f = fso.OpenTextFile(path, 2, True)
    f.WriteLine "@echo off"
    f.WriteLine "chcp 65001 >nul"
    f.WriteLine "title " & title
    f.WriteLine "cd /d """ & dir & """"
    f.WriteLine "echo."
    f.WriteLine "echo  [" & title & "]  Press Ctrl+C to stop"
    f.WriteLine "echo."
    f.WriteLine cmd
    f.Close
End Sub

WriteBat tmp & "\ca_bot.bat",     "Career Agent Bot",  root,                       """" & py & """ agent.py"
WriteBat tmp & "\ca_tracker.bat", "Web Tracker :8080", root,                       """" & py & """ -m uvicorn web.api:app --port 8080 --reload"
WriteBat tmp & "\ca_monitor.bat", "Job Monitor (RSS)", root,                       """" & py & """ services\job-monitor\monitor.py"
WriteBat tmp & "\ca_pdf.bat",     "PDF :8002",         root & "\services\pdf",     """" & py & """ -m uvicorn app:app --port 8002"
WriteBat tmp & "\ca_parser.bat",  "Parser :8001",      root & "\services\parser",  """" & py & """ -m uvicorn app:app --port 8001"

' ── Launch: Windows Terminal (tabs) or fallback to separate windows ──────────
wtExe = shell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Microsoft\WindowsApps\wt.exe"

If fso.FileExists(wtExe) Then
    shell.Run "wt" _
        & " cmd /k """ & tmp & "\ca_bot.bat""" _
        & " ; new-tab cmd /k """ & tmp & "\ca_tracker.bat""" _
        & " ; new-tab cmd /k """ & tmp & "\ca_monitor.bat""" _
        & " ; new-tab cmd /k """ & tmp & "\ca_pdf.bat""" _
        & " ; new-tab cmd /k """ & tmp & "\ca_parser.bat""" _
        , 1, False
Else
    shell.Run "cmd /k """ & tmp & "\ca_bot.bat"""
    WScript.Sleep 400
    shell.Run "cmd /k """ & tmp & "\ca_tracker.bat"""
    WScript.Sleep 400
    shell.Run "cmd /k """ & tmp & "\ca_monitor.bat"""
    WScript.Sleep 400
    shell.Run "cmd /k """ & tmp & "\ca_pdf.bat"""
    WScript.Sleep 400
    shell.Run "cmd /k """ & tmp & "\ca_parser.bat"""
End If

' ── Open tracker in browser after startup ───────────────────────────────────
WScript.Sleep 5000
shell.Run "http://localhost:8080"
