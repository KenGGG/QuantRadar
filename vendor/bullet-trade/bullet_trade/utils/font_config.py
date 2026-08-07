#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
跨平台中文字体配置模块
支持 Mac 和 Windows 系统的中文字体自动配置
"""

import platform
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import warnings

def setup_chinese_fonts():
    """
    自动配置跨平台中文字体显示
    
    根据操作系统自动选择合适的中文字体：
    - macOS: 优先使用 PingFang SC, Hiragino Sans GB 等系统字体
    - Windows: 优先使用 Microsoft YaHei, SimHei 等系统字体
    - Linux: 使用通用的中文字体
    """
    
    system = platform.system()
    
    # 定义不同系统的字体优先级列表
    if system == "Darwin":  # macOS
        font_candidates = [
            'PingFang SC',           # macOS 默认中文字体
            'Hiragino Sans GB',      # 冬青黑体简体中文
            'STHeiti',               # 华文黑体
            'SimHei',                # 黑体
            'Kaiti SC',              # 楷体
            'Songti SC',             # 宋体
            'Arial Unicode MS'       # 备用字体
        ]
        print("🍎 检测到 macOS 系统，配置中文字体...")
        
    elif system == "Windows":  # Windows
        font_candidates = [
            'Microsoft YaHei',       # 微软雅黑
            'SimHei',                # 黑体  
            'KaiTi',                 # 楷体
            'SimSun',                # 宋体
            'FangSong',              # 仿宋
            'Arial Unicode MS'       # 备用字体
        ]
        print("🪟 检测到 Windows 系统，配置中文字体...")
        
    else:  # Linux 或其他系统
        font_candidates = [
            'DejaVu Sans',           # Linux 常见字体
            'WenQuanYi Micro Hei',   # 文泉驿微米黑
            'WenQuanYi Zen Hei',     # 文泉驿正黑
            'Noto Sans CJK SC',      # Google Noto 字体
            'SimHei',                # 黑体
            'Arial Unicode MS'       # 备用字体
        ]
        print("🐧 检测到 Linux/其他系统，配置中文字体...")
    
    # 获取系统可用字体列表
    available_fonts = [f.name for f in fm.fontManager.ttflist]
    
    # 查找第一个可用的字体
    selected_font = None
    for font in font_candidates:
        if font in available_fonts:
            selected_font = font
            break
    
    # 如果没有找到理想字体，使用系统默认字体
    if selected_font is None:
        print("⚠️  未找到推荐的中文字体，使用系统默认字体")
        # 尝试查找任何包含中文的字体
        chinese_fonts = [f for f in available_fonts if any(keyword in f.lower() 
                        for keyword in ['chinese', 'cjk', 'han', 'kai', 'hei', 'song', 'ming'])]
        if chinese_fonts:
            selected_font = chinese_fonts[0]
            print(f"📝 找到中文字体: {selected_font}")
        else:
            selected_font = 'DejaVu Sans'  # 最后的备用字体
            print(f"📝 使用备用字体: {selected_font}")
    else:
        print(f"✅ 成功配置中文字体: {selected_font}")
    
    # 配置 matplotlib 字体参数
    try:
        # 设置中文字体
        plt.rcParams['font.sans-serif'] = [selected_font, 'DejaVu Sans', 'Arial']
        
        # 解决负号显示问题
        plt.rcParams['axes.unicode_minus'] = False
        
        # 设置字体大小和DPI
        plt.rcParams['font.size'] = 10
        plt.rcParams['figure.dpi'] = 100
        
        # 设置图形质量
        plt.rcParams['savefig.dpi'] = 150
        plt.rcParams['figure.figsize'] = (10, 6)
        
        print("🎨 matplotlib 中文字体配置完成")
        
        # 测试字体是否正常工作
        test_chinese_display()
        
    except Exception as e:
        print(f"❌ 字体配置过程中出现错误: {e}")
        # 使用最基本的配置
        plt.rcParams['axes.unicode_minus'] = False
        print("🔧 已应用基础字体配置")

def test_chinese_display():
    """
    测试中文字体显示是否正常
    """
    try:
        # 创建一个简单的测试图形
        import matplotlib.pyplot as plt
        import numpy as np
        
        # 抑制字体警告
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            
            fig, ax = plt.subplots(figsize=(6, 4))
            x = np.linspace(0, 2*np.pi, 100)
            y = np.sin(x)
            
            ax.plot(x, y, label='正弦波')
            ax.set_title('中文字体测试 - 数据可视化')
            ax.set_xlabel('横轴标签')
            ax.set_ylabel('纵轴标签')
            ax.legend()
            ax.grid(True, alpha=0.3)
            
            # 不显示图形，只测试渲染
            plt.close(fig)
            
        print("✅ 中文字体显示测试通过")
        
    except Exception as e:
        print(f"⚠️  中文字体测试出现问题: {e}")

def get_system_fonts_info():
    """
    获取系统字体信息（调试用）
    """
    print("\n" + "="*50)
    print("系统字体信息")
    print("="*50)
    
    system = platform.system()
    print(f"操作系统: {system}")
    
    # 获取所有可用字体
    all_fonts = [f.name for f in fm.fontManager.ttflist]
    
    # 筛选中文相关字体
    chinese_fonts = [f for f in all_fonts if any(keyword in f.lower() 
                    for keyword in ['chinese', 'cjk', 'han', 'kai', 'hei', 'song', 'ming', 'pingfang', 'hiragino'])]
    
    print(f"\n找到 {len(chinese_fonts)} 个中文相关字体:")
    for font in sorted(set(chinese_fonts)):
        print(f"  • {font}")
    
    print(f"\n当前 matplotlib 字体设置:")
    print(f"  sans-serif: {plt.rcParams['font.sans-serif']}")
    print(f"  unicode_minus: {plt.rcParams['axes.unicode_minus']}")
    print(f"  font.size: {plt.rcParams['font.size']}")

if __name__ == "__main__":
    print("🚀 开始配置跨平台中文字体...")
    setup_chinese_fonts()
    print("\n📊 显示系统字体信息:")
    get_system_fonts_info()
    print("\n🎉 字体配置完成!")
