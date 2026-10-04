"""
Protocol Buffers 原始字节解码器与 Antigravity 会话元数据提取器
"""
from typing import Any, Dict, List, Optional, Tuple

def decode_varint(data: bytes, pos: int) -> Tuple[int, int]:
    res = 0
    shift = 0
    while pos < len(data):
        b = data[pos]
        pos += 1
        res |= (b & 0x7F) << shift
        if not (b & 0x80):
            break
        shift += 7
    return res, pos

def parse_proto(data: bytes) -> List[Tuple[int, str, Any]]:
    pos = 0
    fields = []
    data_len = len(data)
    while pos < data_len:
        try:
            tag, pos = decode_varint(data, pos)
        except Exception:
            break
        wire_type = tag & 0x07
        field_num = tag >> 3
        if field_num == 0:
            break
        
        if wire_type == 0:  # Varint
            try:
                val, pos = decode_varint(data, pos)
                fields.append((field_num, 'varint', val))
            except Exception:
                break
        elif wire_type == 1:  # 64-bit
            if pos + 8 > data_len:
                break
            val = data[pos:pos+8]
            pos += 8
            fields.append((field_num, '64bit', val))
        elif wire_type == 2:  # Length-delimited
            try:
                length, pos = decode_varint(data, pos)
            except Exception:
                break
            if pos + length > data_len:
                break
            val = data[pos:pos+length]
            pos += length
            
            sub = None
            try:
                sub = parse_proto(val)
            except Exception:
                sub = None
            
            str_val = None
            try:
                decoded = val.decode('utf-8')
                if all(c.isprintable() or c in '\n\r\t' for c in decoded) and len(decoded) > 0:
                    str_val = decoded
            except Exception:
                str_val = None

            fields.append((field_num, 'len_delimited', {
                'raw': val,
                'str': str_val,
                'sub': sub if sub and len(sub) > 0 else None
            }))
        elif wire_type == 5:  # 32-bit
            if pos + 4 > data_len:
                break
            val = data[pos:pos+4]
            pos += 4
            fields.append((field_num, '32bit', val))
        else:
            break
    return fields

def extract_prompt_breakdown(sub_f10: List[Tuple[int, str, Any]]) -> Dict[str, Any]:
    breakdown = {
        'total_input_reported': 0,
        'system_prompt_tokens': 0,
        'tools_tokens': 0,
        'chat_messages_tokens': 0,
        'details': []
    }
    for fn, wt, v in sub_f10:
        if fn == 1 and wt == 'varint':
            breakdown['total_input_reported'] = v
        elif fn == 3 and wt == 'len_delimited' and v.get('sub'):
            for section in v['sub']:
                if section[0] == 1 and section[1] == 'len_delimited' and section[2].get('sub'):
                    sec_name = None
                    sec_tokens = 0
                    for s_fn, s_wt, s_v in section[2]['sub']:
                        if s_fn == 1 and s_wt == 'len_delimited':
                            sec_name = s_v.get('str')
                        elif s_fn == 4 and s_wt == 'varint':
                            sec_tokens = s_v
                    if sec_name:
                        breakdown['details'].append({'section': sec_name, 'tokens': sec_tokens})
                        if 'System Prompt' in sec_name:
                            breakdown['system_prompt_tokens'] = sec_tokens
                        elif 'Tools' in sec_name:
                            breakdown['tools_tokens'] = sec_tokens
                        elif 'Chat Messages' in sec_name:
                            breakdown['chat_messages_tokens'] = sec_tokens
    return breakdown

def extract_gen_metadata(data: bytes) -> Optional[Dict[str, Any]]:
    if not data:
        return None
    try:
        proto_fields = parse_proto(data)
    except Exception:
        return None
    
    record = {
        'trajectory_id': None,
        'model_id': 'unknown',
        'model_name': 'Unknown',
        'input_tokens': 0,
        'cached_tokens': 0,
        'output_tokens': 0,
        'thinking_tokens': 0,
        'response_tokens': 0,
        'total_tokens': 0,
        'timestamp': None,
        'latency_sec': 0.0,
        'request_id': None,
        'context_window': 0,
        'prompt_breakdown': None
    }
    
    for fn, wt, v in proto_fields:
        if fn == 4 and wt == 'len_delimited' and v.get('str'):
            record['trajectory_id'] = v['str']
        elif fn == 1 and wt == 'len_delimited' and v.get('sub'):
            for sfn, swt, sv in v['sub']:
                if sfn == 19 and swt == 'len_delimited' and sv.get('str'):
                    record['model_id'] = sv['str']
                elif sfn == 21 and swt == 'len_delimited' and sv.get('str'):
                    record['model_name'] = sv['str']
                elif sfn == 4 and swt == 'len_delimited' and sv.get('sub'):
                    # Token 使用信息
                    for t_fn, t_wt, t_v in sv['sub']:
                        if t_fn == 2 and t_wt == 'varint':
                            record['input_tokens'] = t_v
                        elif t_fn == 3 and t_wt == 'varint':
                            record['output_tokens'] = t_v
                        elif t_fn == 5 and t_wt == 'varint':
                            record['cached_tokens'] = t_v
                        elif t_fn == 9 and t_wt == 'varint':
                            record['thinking_tokens'] = t_v
                        elif t_fn == 10 and t_wt == 'varint':
                            record['response_tokens'] = t_v
                        elif t_fn == 11 and t_wt == 'len_delimited' and t_v.get('str'):
                            record['request_id'] = t_v['str']
                elif sfn == 9 and swt == 'len_delimited' and sv.get('sub'):
                    for time_fn, time_wt, time_v in sv['sub']:
                        if time_fn == 4 and time_v.get('sub'):
                            for ts_fn, ts_wt, ts_v in time_v['sub']:
                                if ts_fn == 1 and ts_wt == 'varint':
                                    record['timestamp'] = ts_v
                        elif time_fn == 10 and time_v.get('sub'):
                            for d_fn, d_wt, d_v in time_v['sub']:
                                if d_fn == 4 and d_wt == 'varint':
                                    record['context_window'] = d_v
                            record['prompt_breakdown'] = extract_prompt_breakdown(time_v['sub'])
                elif sfn == 11 and swt == 'len_delimited' and sv.get('sub'):
                    s = 0
                    ns = 0
                    for lat_fn, lat_wt, lat_v in sv['sub']:
                        if lat_fn == 1 and lat_wt == 'varint':
                            s = lat_v
                        elif lat_fn == 2 and lat_wt == 'varint':
                            ns = lat_v
                    record['latency_sec'] = round(s + ns / 1e9, 3)

    # 规范化 response_tokens
    if record['response_tokens'] == 0 and record['output_tokens'] > 0:
        record['response_tokens'] = max(0, record['output_tokens'] - record['thinking_tokens'])
    
    # 计算总 token
    # 总 Token = 未缓存输入 + 缓存读取 + 输出
    record['total_tokens'] = record['input_tokens'] + record['cached_tokens'] + record['output_tokens']

    # 统一模型名称展示
    if record['model_name'] == 'Unknown' and record['model_id'] != 'unknown':
        id_map = {
            'gemini-default': 'Gemini 3.5 Flash (Medium)',
            'gemini-3-flash-a': 'Gemini 3 Flash (Alpha)',
            'gemini-3-flash-medium-a': 'Gemini 3 Flash Medium (Alpha)',
            'gemini-3.6-flash': 'Gemini 3.6 Flash (Medium)',
            'gemini-3.7-flash': 'Gemini 3.7 Flash (Medium)',
            'gemini-3.8-flash': 'Gemini 3.8 Flash (Medium)',
            'gemini-3p7-flash-exp-d': 'Gemini 3.7 Flash Exp (Thinking)',
            'claude-opus-4-6-thinking': 'Claude Opus 4.6 (Thinking)',
        }
        record['model_name'] = id_map.get(record['model_id'], record['model_id'])

    return record
