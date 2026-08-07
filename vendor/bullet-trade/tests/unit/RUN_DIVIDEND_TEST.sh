#!/bin/bash
# 分红数据一致性测试 - 快速运行脚本

echo "================================"
echo "分红数据一致性测试"
echo "================================"
echo ""

# 1. 快速单元测试（不需要网络）
echo "1. 运行单元测试（不需要网络）..."
python -m pytest bullet-trade/tests/unit/test_dividend_data_consistency.py -m unit -v

if [ $? -ne 0 ]; then
    echo ""
    echo "❌ 单元测试失败！"
    exit 1
fi

echo ""
echo "✅ 单元测试通过！"
echo ""

# 2. 网络测试（需要配置环境变量）
echo "2. 运行网络测试..."
echo "   提示：确保已配置环境变量 JQDATA_USERNAME, QMT_DATA_PATH 或 TUSHARE_TOKEN"
echo ""

# 检查是否配置了任何数据源
if [ -z "$JQDATA_USERNAME" ] && [ -z "$QMT_DATA_PATH" ] && [ -z "$TUSHARE_TOKEN" ]; then
    echo "⚠️  警告：未检测到任何数据源环境变量，跳过网络测试"
    echo ""
    echo "请配置以下环境变量之一："
    echo "  - JQDATA_USERNAME 和 JQDATA_PASSWORD"
    echo "  - QMT_DATA_PATH"
    echo "  - TUSHARE_TOKEN"
    exit 0
fi

# 构建 --live-providers 参数
PROVIDERS=""
if [ -n "$JQDATA_USERNAME" ]; then
    PROVIDERS="jqdata"
fi
if [ -n "$QMT_DATA_PATH" ]; then
    if [ -n "$PROVIDERS" ]; then
        PROVIDERS="$PROVIDERS,miniqmt"
    else
        PROVIDERS="miniqmt"
    fi
fi
if [ -n "$TUSHARE_TOKEN" ]; then
    if [ -n "$PROVIDERS" ]; then
        PROVIDERS="$PROVIDERS,tushare"
    else
        PROVIDERS="tushare"
    fi
fi

echo "   检测到可用的数据源：$PROVIDERS"
echo ""

python -m pytest bullet-trade/tests/unit/test_dividend_data_consistency.py -m requires_network --live-providers="$PROVIDERS" -v

if [ $? -ne 0 ]; then
    echo ""
    echo "❌ 网络测试失败！请检查错误信息。"
    exit 1
fi

echo ""
echo "✅ 所有测试通过！"
echo ""
echo "================================"
echo "测试完成"
echo "================================"

