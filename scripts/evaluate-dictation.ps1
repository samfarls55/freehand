#Requires -Version 7.0
param(
    [Parameter(Mandatory)][string]$App,
    [Parameter(Mandatory)][string]$Manifest,
    [Parameter(Mandatory)][string]$Output,
    [string]$ModelSource,
    [string]$Dotnet,
    [ValidateRange(1,20)][int]$Repeat = 1,
    [ValidateRange(1,300)][int]$CompletionTimeoutSeconds = 180,
    [string]$Gains = '1',
    [switch]$Realtime,
    [switch]$Cold,
    [switch]$IncludeText
)
. (Join-Path $PSScriptRoot 'common.ps1')
$dotnetPath = Resolve-FreehandDotnet $Dotnet
$model = Find-FreehandModelDirectory $ModelSource
if (-not $model) { throw 'Model files were not found.' }
$appPath = (Resolve-Path -LiteralPath $App).Path
$manifestPath = (Resolve-Path -LiteralPath $Manifest).Path
$outputPath = [IO.Path]::GetFullPath($Output)
$project = Join-Path $projectRoot 'tools/Freehand.Evaluation/Freehand.Evaluation.csproj'
& $dotnetPath build $project -c Release -warnaserror
if ($LASTEXITCODE -ne 0) { throw 'Evaluator build failed.' }
$arguments = @((Join-Path $projectRoot 'tools/Freehand.Evaluation/bin/Release/net10.0/Freehand.Evaluation.dll'), $appPath, $model, $manifestPath, $outputPath, '--repeat', $Repeat, '--gains', $Gains, '--completion-timeout-seconds', $CompletionTimeoutSeconds)
if ($Realtime) { $arguments += '--realtime' }
if ($Cold) { $arguments += '--cold' }
if ($IncludeText) { $arguments += '--include-text' }
& $dotnetPath @arguments
if ($LASTEXITCODE -ne 0) { throw 'Dictation evaluation failed. See the output report.' }
