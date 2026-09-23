' ---------------------------------------------------------------------------
'  Double-click entry point for the case dashboard -- no console window.
'
'  The dashboard opens in a chromeless browser *application* window, and that
'  window owns the server's lifetime: close the window and the server goes with
'  it.  Nothing is left running in the background and there is no console that
'  has to be kept open.
'
'  Double-clicking it twice is safe: the second one just hands the URL back to
'  the instance already running.  To watch the startup on screen instead, run
'  `python caseDashboard/launcher/run.py --window` from a terminal.
'
'  Keep this file CRLF and English-only: Windows Script Host reads .vbs as ANSI,
'  so non-ASCII text in here would come out garbled.
' ---------------------------------------------------------------------------
Option Explicit

Const TITLE = "case dashboard"

Dim shell, fso, repoDir, runPy, logPath, interpreter, rc

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

' ...\caseDashboard\dashboard.vbs -> the repository root
repoDir = fso.GetParentFolderName(fso.GetParentFolderName(WScript.ScriptFullName))
runPy = fso.BuildPath(repoDir, "caseDashboard\launcher\run.py")
logPath = fso.BuildPath(repoDir, "caseDashboard\.cache\launcher.log")

If Not fso.FileExists(runPy) Then
    MsgBox "Cannot find the dashboard launcher:" & vbCrLf & runPy, vbCritical, TITLE
    WScript.Quit 1
End If

interpreter = WindowedPython()

shell.CurrentDirectory = repoDir

' SW_HIDE (0), and wait: run.py hands control back when the dashboard window is
' closed, so this script is the one thing watching the dashboard's lifetime.
rc = shell.Run(interpreter & " """ & runPy & """ --window", 0, True)

If rc <> 0 Then
    MsgBox "The dashboard stopped with exit code " & rc & "." & vbCrLf & vbCrLf & _
           "Log: " & logPath & vbCrLf & vbCrLf & _
           "If the window never appeared, read the log, or run " & _
           "`python caseDashboard\launcher\run.py --window` in a terminal.", _
           vbCritical, TITLE
End If

' ---------------------------------------------------------------------------
' The windowed Python: no console, so nothing flashes on screen.
'
' Preference order: the ``py`` launcher first, then any Python installed for
' this user, then whatever Windows finds on PATH.
' Returns the interpreter command, already quoted.
' ---------------------------------------------------------------------------
Function WindowedPython()
    Dim sh, files, candidate, root, folder

    Set sh = CreateObject("WScript.Shell")
    Set files = CreateObject("Scripting.FileSystemObject")

    candidate = sh.ExpandEnvironmentStrings("%WINDIR%\pyw.exe")
    If files.FileExists(candidate) Then
        WindowedPython = """" & candidate & """ -3"
        Exit Function
    End If

    root = sh.ExpandEnvironmentStrings("%LOCALAPPDATA%\Programs\Python")
    If files.FolderExists(root) Then
        For Each folder In files.GetFolder(root).SubFolders
            candidate = files.BuildPath(folder.Path, "pythonw.exe")
            If files.FileExists(candidate) Then
                WindowedPython = """" & candidate & """"
                Exit Function
            End If
        Next
    End If

    ' Let Windows resolve it on PATH; if that fails too, run.py reports it.
    WindowedPython = "pythonw.exe"
End Function
