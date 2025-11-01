import xml.etree.ElementTree as ET
import os
import subprocess
import re
import sys
from datetime import timedelta
import tempfile
import math
from collections import defaultdict

def parse_bilibili_xml_to_ass(xml_file, ass_file, video_width=720, video_height=1280):
    """解析B站XML弹幕文件并转换为ASS字幕文件，确保所有弹幕显示且不重叠"""
    
    # 针对720x1280分辨率优化参数
    base_font_size = 28
    track_spacing = 32
    track_count = 20  # 减少轨道数量，确保间距足够
    
    print(f"视频分辨率: {video_width}x{video_height}")
    print(f"字体大小: {base_font_size}px")
    print(f"轨道间距: {track_spacing}px")
    print(f"轨道数量: {track_count}")
    
    try:
        tree = ET.parse(xml_file)
        root = tree.getroot()
    except Exception as e:
        print(f"解析XML文件失败: {e}")
        return False
    
    # 使用指定的昵称颜色 #FF8FA3，并添加小边框
    ass_header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {video_width}
PlayResY: {video_height}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,{base_font_size},&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,0,2,10,10,10,1
Style: Username,Arial,{base_font_size},&H00A38FFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,0,2,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    
    # 收集所有弹幕
    danmakus = []
    
    for elem in root.iter('d'):
        p_attrs = elem.get('p', '').split(',')
        if len(p_attrs) >= 1:
            try:
                start_time = float(p_attrs[0])
                user = elem.get('user', '用户')
                content = elem.text if elem.text else ""
                
                if not content.strip():
                    continue
                
                # 处理特殊字符
                content = content.replace('\\', '\\\\').replace('{', '\\{').replace('}', '\\}')
                user = user.replace('\\', '\\\\').replace('{', '\\{').replace('}', '\\}')
                
                danmakus.append({
                    'start_time': start_time,
                    'user': user,
                    'content': content
                })
            except (ValueError, IndexError):
                continue
    
    # 按时间排序
    danmakus.sort(key=lambda x: x['start_time'])
    
    # 分析弹幕时间分布
    if danmakus:
        total_duration = danmakus[-1]['start_time'] - danmakus[0]['start_time']
        print(f"弹幕时间范围: {danmakus[0]['start_time']:.2f}s - {danmakus[-1]['start_time']:.2f}s")
        print(f"弹幕总时长: {total_duration:.2f}s")
        print(f"弹幕密度: {len(danmakus) / max(total_duration, 1):.2f} 条/秒")
    
    with open(ass_file, 'w', encoding='utf-8-sig') as f:
        f.write(ass_header)
        
        # 使用基于时间窗口的弹幕分配系统
        base_y = video_height * 0.7  # 基础Y位置
        max_y = video_height * 1   # 最大Y位置
        
        # 创建时间窗口，每个窗口持续2秒
        time_windows = defaultdict(list)
        window_duration = 2.0
        
        # 将弹幕分配到时间窗口
        for danmaku in danmakus:
            window_index = int(danmaku['start_time'] / window_duration)
            time_windows[window_index].append(danmaku)
        
        # 处理每个时间窗口
        processed_danmakus = []
        
        for window_index, window_danmakus in sorted(time_windows.items()):
            # 对窗口内的弹幕按时间排序
            window_danmakus.sort(key=lambda x: x['start_time'])
            
            # 计算窗口内弹幕的密度
            density = len(window_danmakus) / window_duration
            print(f"时间窗口 {window_index}: {len(window_danmakus)} 条弹幕, 密度: {density:.2f} 条/秒")
            
            # 如果密度过高，调整弹幕的起始时间
            if density > track_count / 2:  # 如果密度超过轨道数的一半
                # 在窗口内均匀分布弹幕
                time_step = window_duration / len(window_danmakus)
                for i, danmaku in enumerate(window_danmakus):
                    # 在窗口内均匀分布弹幕时间
                    new_start_time = window_index * window_duration + i * time_step
                    danmaku['adjusted_start_time'] = new_start_time
            else:
                # 保持原时间
                for danmaku in window_danmakus:
                    danmaku['adjusted_start_time'] = danmaku['start_time']
            
            processed_danmakus.extend(window_danmakus)
        
        # 按调整后的时间重新排序
        processed_danmakus.sort(key=lambda x: x['adjusted_start_time'])
        
        # 使用简单的轨道轮换系统
        track_usage = [0] * track_count  # 记录每个轨道的使用次数
        current_track = 0
        
        for danmaku in processed_danmakus:
            start_time = danmaku['adjusted_start_time']
            user = danmaku['user']
            content = danmaku['content']
            
            # 根据内容长度调整持续时间
            text_length = len(user) + len(content)
            base_duration = 8
            length_factor = text_length * 0.1
            duration = min(max(base_duration + length_factor, 6), 15)+12
            
            # 选择轨道 - 使用简单的轮换，确保均匀分布
            track = current_track
            track_usage[track] += 1
            
            # 更新下一个轨道
            current_track = (current_track + 1) % track_count
            
            # 计算垂直位置
            y_position = base_y + track * track_spacing
            
            # 确保不会超出屏幕底部
            if y_position > max_y:
                y_position = base_y + (track % (track_count // 2)) * track_spacing
            
            # 格式化时间
            start_timedelta = timedelta(seconds=start_time)
            end_timedelta = timedelta(seconds=start_time + duration)
            
            start_ass_time = f"{start_timedelta.seconds // 3600:01d}:{(start_timedelta.seconds % 3600) // 60:02d}:{start_timedelta.seconds % 60:02d}.{start_timedelta.microseconds // 10000:02d}"
            end_ass_time = f"{end_timedelta.seconds // 3600:01d}:{(end_timedelta.seconds % 3600) // 60:02d}:{end_timedelta.seconds % 60:02d}.{end_timedelta.microseconds // 10000:02d}"
            
            # 计算起始和结束位置
            start_x = video_width + 200  # 固定起始位置，确保从屏幕外开始
            end_x = -1000  # 固定结束位置
            
            # 使用样式切换 - 指定颜色昵称，白色内容，小边框
            danmaku_text = f"{{\\move({start_x},{int(y_position)},{end_x},{int(y_position)})}}{{\\rUsername}}{user}: {{\\rDefault}}{content}"
            
            f.write(f"Dialogue: 0,{start_ass_time},{end_ass_time},Default,,0,0,0,,{danmaku_text}\n")
        
        # 输出轨道使用统计
        print(f"\n轨道使用统计:")
        for i, count in enumerate(track_usage):
            print(f"  轨道 {i}: {count} 条弹幕")
        print(f"  总弹幕数: {len(processed_danmakus)} 条")
    
    print(f"成功转换弹幕，共 {len(processed_danmakus)} 条")
    print(f"生成的ASS文件: {ass_file}")
    
    return True

def get_video_duration(video_file):
    """获取视频时长"""
    try:
        cmd = ['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration', 
               '-of', 'default=noprint_wrappers=1:nokey=1', video_file]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(result.stdout.strip())
    except:
        return 0

def show_progress_bar(progress, total, bar_length=50):
    """显示进度条"""
    percent = progress / total
    arrow = '=' * int(round(percent * bar_length) - 1) + '>'
    spaces = ' ' * (bar_length - len(arrow))
    
    sys.stdout.write(f'\r进度: [{arrow + spaces}] {int(percent * 100)}%')
    sys.stdout.flush()

def merge_video_with_ass_optimized(video_file, ass_file, output_file, mode="fast"):
    """使用优化的FFmpeg命令合并视频与ASS字幕"""
    
    if not os.path.exists(video_file):
        print(f"视频文件不存在: {video_file}")
        return False
    
    if not os.path.exists(ass_file):
        print(f"ASS文件不存在: {ass_file}")
        return False
    
    # 获取视频时长用于进度显示
    duration = get_video_duration(video_file)
    
    # 构建优化的FFmpeg命令 - 不使用CUDA，使用CPU优化
    if mode == "ultrafast":
        # 超快速模式 - 牺牲质量换取速度
        ffmpeg_cmd = [
            'ffmpeg', '-y',
            '-i', video_file,
            '-vf', f'ass={ass_file}',
            '-c:a', 'copy',  # 直接复制音频，不重新编码
            '-c:v', 'libx264',
            '-preset', 'ultrafast',  # 最快速的预设
            '-crf', '25',            # 稍微降低质量
            '-threads', '0',         # 使用所有CPU线程
            '-x264-params', 'keyint=30:min-keyint=30:scenecut=0',  # 减少关键帧
            output_file
        ]
        print("使用超快速CPU编码模式")
    else:
        # 快速模式 - 平衡质量和速度
        ffmpeg_cmd = [
            'ffmpeg', '-y',
            '-i', video_file,
            '-vf', f'ass={ass_file}',
            '-c:a', 'aac', '-b:a', '128k',
            '-c:v', 'libx264',
            '-preset', 'veryfast',   # 非常快速的预设
            '-crf', '23',            # 标准质量
            '-threads', '0',         # 使用所有CPU线程
            '-movflags', '+faststart',  # 优化网络播放
            '-x264-params', 'keyint=60:min-keyint=30:scenecut=40',  # 优化关键帧
            output_file
        ]
        print("使用快速CPU编码模式")
    
    try:
        print("开始合并视频和弹幕...")
        print("FFmpeg命令:", ' '.join(ffmpeg_cmd))
        
        # 运行FFmpeg并捕获进度
        process = subprocess.Popen(
            ffmpeg_cmd,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            bufsize=1,
            encoding='utf-8',
            errors='replace'
        )
        
        # 正则表达式匹配进度
        duration_pattern = re.compile(r'time=(\d+):(\d+):(\d+\.\d+)')
        
        while True:
            line = process.stderr.readline()
            if not line and process.poll() is not None:
                break
                
            if line:
                # 检查进度信息
                match = duration_pattern.search(line)
                if match and duration > 0:
                    hours, minutes, seconds = match.groups()
                    current_time = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
                    progress = min(current_time / duration, 1.0)
                    show_progress_bar(progress, 1.0)
                
                # 打印其他重要信息
                if 'error' in line.lower() or 'fail' in line.lower():
                    if 'font' not in line.lower() and 'memory' not in line.lower():
                        print(f"\n错误信息: {line.strip()}")
        
        process.wait()
        
        if process.returncode == 0:
            print(f"\n✅ 成功生成输出文件: {output_file}")
            return True
        else:
            print(f"\n❌ FFmpeg执行失败，返回码: {process.returncode}")
            return False
            
    except Exception as e:
        print(f"\n❌ FFmpeg执行错误: {e}")
        return False

def create_test_ass_file(ass_file, video_width=720, video_height=1280):
    """创建一个测试ASS文件，用于验证弹幕分布效果"""
    content = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {video_width}
PlayResY: {video_height}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,36,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,0,2,10,10,10,1
Style: Username,Arial,36,&H00A38FFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,0,2,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:01.00,0:00:10.00,Default,,0,0,0,,{{\\move(920,800,-1000,800)}}{{\\rUsername}}测试用户1{{\\rDefault}}: 测试弹幕1
Dialogue: 0,0:00:01.50,0:00:10.50,Default,,0,0,0,,{{\\move(920,850,-1000,850)}}{{\\rUsername}}测试用户2{{\\rDefault}}: 测试弹幕2
Dialogue: 0,0:00:02.00,0:00:11.00,Default,,0,0,0,,{{\\move(920,900,-1000,900)}}{{\\rUsername}}测试用户3{{\\rDefault}}: 测试弹幕3
Dialogue: 0,0:00:02.50,0:00:11.50,Default,,0,0,0,,{{\\move(920,800,-1000,800)}}{{\\rUsername}}测试用户4{{\\rDefault}}: 测试弹幕4
Dialogue: 0,0:00:03.00,0:00:12.00,Default,,0,0,0,,{{\\move(920,850,-1000,850)}}{{\\rUsername}}测试用户5{{\\rDefault}}: 测试弹幕5
Dialogue: 0,0:00:03.50,0:00:12.50,Default,,0,0,0,,{{\\move(920,900,-1000,900)}}{{\\rUsername}}测试用户6{{\\rDefault}}: 测试弹幕6
Dialogue: 0,0:00:04.00,0:00:13.00,Default,,0,0,0,,{{\\move(920,800,-1000,800)}}{{\\rUsername}}测试用户7{{\\rDefault}}: 测试弹幕7
Dialogue: 0,0:00:04.50,0:00:13.50,Default,,0,0,0,,{{\\move(920,850,-1000,850)}}{{\\rUsername}}测试用户8{{\\rDefault}}: 测试弹幕8
Dialogue: 0,0:00:05.00,0:00:14.00,Default,,0,0,0,,{{\\move(920,900,-1000,900)}}{{\\rUsername}}测试用户9{{\\rDefault}}: 测试弹幕9
"""
    
    with open(ass_file, 'w', encoding='utf-8-sig') as f:
        f.write(content)
    print(f"创建测试ASS文件: {ass_file}")

def main():
    # 配置参数
    xml_file = "mycc.xml"
    video_file = "mycc.ts"
    output_file = "mycc_output.mp4"
    
    # 使用720x1280分辨率
    video_width, video_height = 720, 1280
    
    print(f"使用分辨率: {video_width}x{video_height}")
    
    # 可选：创建测试ASS文件验证弹幕分布效果
    create_test_ass_file("test_distribution.ass", video_width, video_height)
    print("已创建测试文件 'test_distribution.ass'，您可以先用它测试弹幕分布效果")
    
    # 生成临时ASS文件
    ass_file = "temp_danmaku.ass"
    
    print("开始处理弹幕...")
    
    # Step 1: XML转ASS
    if parse_bilibili_xml_to_ass(xml_file, ass_file, video_width, video_height):
        print("弹幕转换完成")
        
        # 让用户选择处理速度
        print("\n请选择处理速度:")
        print("1. 快速模式 (推荐)")
        print("2. 超快速模式 (最快，但质量稍低)")
        
        choice = input("请输入选择 (1 或 2): ").strip()
        
        if choice == "2":
            mode = "ultrafast"
        else:
            mode = "fast"
        
        # Step 2: 合并视频和ASS
        success = merge_video_with_ass_optimized(video_file, ass_file, output_file, mode)
        
        if success:
            print("视频合并完成")
            
            # 清理临时文件
            try:
                os.remove(ass_file)
                print("临时文件已清理")
            except:
                pass
        else:
            print("视频合并失败")
    else:
        print("弹幕转换失败")

if __name__ == "__main__":
    main()