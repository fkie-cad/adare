############################################
# AdareVM windows setup
############################################

## install chocolatey
Set-ExecutionPolicy Bypass -Scope Process -Force; [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; iex ((New-Object System.Net.WebClient).DownloadString('https://chocolatey.org/install.ps1'))

## install python3.10
choco install python --version=3.10.0 -y

## install pip via python
python -m pip install --upgrade pip

## install poetry use fork since the original is not working for windows (see https://github.com/python-poetry/install.python-poetry.org/issues/112)
(Invoke-WebRequest -Uri https://raw.githubusercontent.com/fdcastel/install-poetry/main/install-poetry.py -UseBasicParsing).Content | py -

## add poetry to path permanently
$poetryPath = "$env:USERPROFILE\AppData\Roaming\Python\Scripts"
$newPath = [System.Environment]::GetEnvironmentVariable('Path', [System.EnvironmentVariableTarget]::Machine) + ";$poetryPath"
[System.Environment]::SetEnvironmentVariable('Path', $newPath, [System.EnvironmentVariableTarget]::Machine)