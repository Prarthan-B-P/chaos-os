# Converts a .docx to PDF with Microsoft Word, refreshing the table of contents first.
#   powershell -ExecutionPolicy Bypass -File docs\study-guide\to-pdf.ps1 -Docx <file.docx>
param([Parameter(Mandatory = $true)][string]$Docx)
$ErrorActionPreference = "Stop"
$full = (Resolve-Path $Docx).Path
$pdf = [System.IO.Path]::ChangeExtension($full, ".pdf")
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
try {
    $doc = $word.Documents.Open($full, $false, $false)
    foreach ($toc in $doc.TablesOfContents) { $toc.Update() }
    $doc.Fields.Update() | Out-Null
    $doc.Save()                       # keep the refreshed contents in the .docx too
    $doc.ExportAsFixedFormat($pdf, 17) # 17 = wdExportFormatPDF
    $pages = $doc.ComputeStatistics(2) # 2 = wdStatisticPages
    $doc.Close($false)
    Write-Host "wrote $pdf ($pages pages)"
}
finally {
    try { $word.Quit() } catch { }   # Word sometimes exits on its own after closing the document
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null
}
