$vsdev = 'C:\Program Files\Microsoft Visual Studio\18\Community\Common7\Tools\VsDevCmd.bat'
$cmake = 'C:\Program Files\Microsoft Visual Studio\18\Community\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe'
$src   = 'C:\Users\RevanParimi\OneDrive - IBM\Documents\Gen AI Projects\StockAgent-main\cpp'
$build = 'C:\Users\RevanParimi\OneDrive - IBM\Documents\Gen AI Projects\StockAgent-main\cpp\build'

Write-Host "=== Configuring ===" -ForegroundColor Cyan
& cmd /c "`"$vsdev`" && `"$cmake`" -S `"$src`" -B `"$build`" -DCMAKE_BUILD_TYPE=Release"
if ($LASTEXITCODE -ne 0) { Write-Error "Configure failed"; exit 1 }

Write-Host "=== Building ===" -ForegroundColor Cyan
& cmd /c "`"$vsdev`" && `"$cmake`" --build `"$build`" --config Release"
if ($LASTEXITCODE -ne 0) { Write-Error "Build failed"; exit 1 }

Write-Host "=== Installing (copy .pyd to project root) ===" -ForegroundColor Cyan
& cmd /c "`"$vsdev`" && `"$cmake`" --install `"$build`" --config Release"
if ($LASTEXITCODE -ne 0) { Write-Error "Install failed"; exit 1 }

Write-Host "=== Done ===" -ForegroundColor Green
