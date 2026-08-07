@echo off
REM 分红数据一致性测试 - Windows 批处理脚本

echo ================================
echo 分红数据一致性测试
echo ================================
echo.

REM 1. 快速单元测试（不需要网络）
echo 1. 运行单元测试（不需要网络）...
python -m pytest bullet-trade/tests/unit/test_dividend_data_consistency.py -m unit -v

if errorlevel 1 (
    echo.
    echo ❌ 单元测试失败！
    exit /b 1
)

echo.
echo ✅ 单元测试通过！
echo.

REM 2. 网络测试（需要配置环境变量）
echo 2. 运行网络测试...
echo    提示：确保已配置环境变量 JQDATA_USERNAME, QMT_DATA_PATH 或 TUSHARE_TOKEN
echo.

REM 检查是否配置了任何数据源
set "HAS_PROVIDER=0"
if not "%JQDATA_USERNAME%"=="" set "HAS_PROVIDER=1"
if not "%QMT_DATA_PATH%"=="" set "HAS_PROVIDER=1"
if not "%TUSHARE_TOKEN%"=="" set "HAS_PROVIDER=1"

if "%HAS_PROVIDER%"=="0" (
    echo ⚠️  警告：未检测到任何数据源环境变量，跳过网络测试
    echo.
    echo 请配置以下环境变量之一：
    echo   - JQDATA_USERNAME 和 JQDATA_PASSWORD
    echo   - QMT_DATA_PATH
    echo   - TUSHARE_TOKEN
    exit /b 0
)

REM 构建 --live-providers 参数
set "PROVIDERS="
if not "%JQDATA_USERNAME%"=="" set "PROVIDERS=jqdata"
if not "%QMT_DATA_PATH%"=="" (
    if not "%PROVIDERS%"=="" (
        set "PROVIDERS=%PROVIDERS%,miniqmt"
    ) else (
        set "PROVIDERS=miniqmt"
    )
)
if not "%TUSHARE_TOKEN%"=="" (
    if not "%PROVIDERS%"=="" (
        set "PROVIDERS=%PROVIDERS%,tushare"
    ) else (
        set "PROVIDERS=tushare"
    )
)

echo    检测到可用的数据源：%PROVIDERS%
echo.

python -m pytest bullet-trade/tests/unit/test_dividend_data_consistency.py -m requires_network --live-providers=%PROVIDERS% -v

if errorlevel 1 (
    echo.
    echo ❌ 网络测试失败！请检查错误信息。
    exit /b 1
)

echo.
echo ✅ 所有测试通过！
echo.
echo ================================
echo 测试完成
echo ================================

