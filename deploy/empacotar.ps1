# Gera roleflix-deploy.tar.gz na pasta acima do projeto, sem segredos, banco, fotos ou ambiente local.
$projeto = Split-Path -Parent $PSScriptRoot
$destino = Join-Path (Split-Path -Parent $projeto) "roleflix-deploy.tar.gz"
tar -czf $destino -C $projeto --exclude=.env --exclude=db.sqlite3 --exclude=media --exclude=venv --exclude=.venv --exclude=__pycache__ --exclude=staticfiles --exclude=data --exclude=backups .
Write-Output "Pacote criado em $destino"
