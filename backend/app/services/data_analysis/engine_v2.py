"""
经营分析 V2 — 多表灵活分析引擎
支持：1-5个表上传 → 关联合并 → 自定义维度聚合 → 报告生成
"""
import os, json, base64, hashlib, logging, tempfile
from datetime import datetime
from pathlib import Path
from io import BytesIO
from collections import defaultdict

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
plt.rcParams['font.sans-serif'] = ['WenQuanYi Zen Hei','Noto Sans CJK JP','DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

logger = logging.getLogger(__name__)

# ─── 色板 ───
CLR = ['#2563eb','#10b981','#f59e0b','#ef4444','#8b5cf6',
       '#ec4899','#14b8a6','#f97316','#06b6d4','#84cc16',
       '#6366f1','#d946ef','#0ea5e9','#22c55e','#eab308',
       '#a855f7','#3b82f6','#34d399','#fb923c','#f472b6']

# ─── 颜色映射：为每个唯一值分配稳定颜色 ───
def _color_map(values):
    seen = {}
    for i, v in enumerate(values):
        if v not in seen:
            seen[v] = CLR[i % len(CLR)]
    return seen


class MultiTableAnalyzer:
    """多表灵活分析引擎"""

    def __init__(self, work_dir: str = None):
        self.work_dir = work_dir or tempfile.mkdtemp(prefix='analysis_v2_')
        self.chart_dir = os.path.join(self.work_dir, 'charts')
        os.makedirs(self.chart_dir, exist_ok=True)
        self.tables = {}        # table_id → DataFrame
        self.meta = {}          # table_id → {columns, dtypes, rows}

    # ────────────────────────────────────────────
    # 加载
    # ────────────────────────────────────────────
    def load_table(self, file_path: str, table_id: str = None) -> dict:
        """加载一个Excel/CSV文件，返回schema信息"""
        ext = Path(file_path).suffix.lower()
        if ext == '.csv':
            df = pd.read_csv(file_path)
        else:
            df = pd.read_excel(file_path, engine='openpyxl')

        # 清洗列名
        df.columns = [str(c).strip() for c in df.columns]
        # 去掉全空列
        df = df.dropna(axis=1, how='all')

        tid = table_id or hashlib.md5(file_path.encode()).hexdigest()[:8]
        self.tables[tid] = df

        schema = self._schema(df)
        self.meta[tid] = schema
        logger.info(f"加载表 {tid}: {schema['cols']}列 × {len(df)}行")
        return {**schema, 'table_id': tid, 'rows': len(df)}

    def _schema(self, df: pd.DataFrame) -> dict:
        """提取schema信息"""
        cols = []
        for c in df.columns:
            dtype = str(df[c].dtype)
            # 推断实际类型
            if pd.api.types.is_numeric_dtype(df[c]):
                vtype = '数值'
            elif pd.api.types.is_datetime64_any_dtype(df[c]):
                vtype = '日期'
            else:
                try:
                    pd.to_datetime(df[c], format='mixed')
                    vtype = '日期'
                except:
                    vtype = '文本'
            cols.append({
                'name': c,
                'dtype': dtype,
                'type': vtype,
                'non_null': int(df[c].notna().sum()),
                'unique': int(df[c].nunique()),
            })
        return {
            'cols': len(cols),
            'columns': cols,
        }

    def preview(self, table_id: str, n: int = 20) -> list:
        """返回前n行数据"""
        if table_id not in self.tables:
            raise ValueError(f"表 {table_id} 不存在")
        df = self.tables[table_id].head(n)
        return json.loads(df.to_json(orient='records', force_ascii=False))

    # ────────────────────────────────────────────
    # 关联合并
    # ────────────────────────────────────────────
    def merge(self, joins: list) -> pd.DataFrame:
        """按关联规则合并多个表
        joins: [{left_table, left_col, right_table, right_col, how:'left'|'inner'}]
        """
        if len(self.tables) < 1:
            raise ValueError("至少需要1个表")

        # 以第一个表为基准
        ids = list(self.tables.keys())
        result = self.tables[ids[0]].copy()

        for j in joins:
            lt = j['left_table']
            rc = j['right_col']
            lc = j['left_col']
            rt = j['right_table']
            how = j.get('how', 'left')

            if lt not in self.tables or rt not in self.tables:
                raise ValueError(f"表不存在: {lt}/{rt}")

            # 类型统一（避免int vs object join问题）
            left_df = self.tables[lt]
            right_df = self.tables[rt]
            if lc in left_df.columns and rc in right_df.columns:
                if left_df[lc].dtype != right_df[rc].dtype:
                    try:
                        right_df[rc] = right_df[rc].astype(str)
                        left_df[lc] = left_df[lc].astype(str)
                    except:
                        pass

            result = result.merge(
                right_df,
                how=how,
                left_on=lc,
                right_on=rc,
                suffixes=('', f'_{rt}')
            )

        logger.info(f"合并完成: {len(result)}行 × {len(result.columns)}列")
        return result

    # ────────────────────────────────────────────
    # 自定义维度聚合
    # ────────────────────────────────────────────
    def aggregate(self, df: pd.DataFrame,
                  row_dims: list = None,
                  col_dims: list = None,
                  values: list = None,
                  filters: list = None) -> dict:
        """按用户指定维度进行聚合

        row_dims: [{column, label}] — 行维度（分组字段）
        col_dims: [{column, label}] — 列维度（子分组，可选）
        values: [{column, agg, label}] — 聚合值
        filters: [{column, op, value}] — 过滤器
        """
        row_dims = row_dims or []
        col_dims = col_dims or []
        values = values or []
        filters = filters or []

        # 应用过滤器
        for f in filters:
            col, op, val = f['column'], f.get('op', 'eq'), f.get('value')
            if col not in df.columns:
                continue
            if op == 'eq':
                df = df[df[col] == val]
            elif op == 'neq':
                df = df[df[col] != val]
            elif op == 'gt':
                df = df[df[col] > float(val)]
            elif op == 'gte':
                df = df[df[col] >= float(val)]
            elif op == 'lt':
                df = df[df[col] < float(val)]
            elif op == 'lte':
                df = df[df[col] <= float(val)]
            elif op == 'in':
                vals = val.split(',') if isinstance(val, str) else val
                df = df[df[col].isin(vals)]

        # 分组字段
        group_cols = [d['column'] for d in row_dims]
        if col_dims:
            group_cols.append(col_dims[0]['column'])

        # 如果没有聚合值，用计数
        if not values:
            if group_cols:
                agg_result = df.groupby(group_cols).size().reset_index(name='计数')
            else:
                agg_result = pd.DataFrame({'计数': [len(df)]})
        else:
            agg_dict = {}
            for v in values:
                col = v['column']
                agg = v.get('agg', 'sum')
                if col in df.columns:
                    # 确保数值类型
                    if agg in ('sum','avg','mean','min','max'):
                        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
                    agg_dict[col] = agg

            if group_cols:
                if agg_dict:
                    agg_result = df.groupby(group_cols).agg(agg_dict).reset_index()
                else:
                    agg_result = df.groupby(group_cols).size().reset_index(name='计数')
            else:
                if agg_dict:
                    agg_result = df.agg(agg_dict).to_frame().T
                else:
                    agg_result = pd.DataFrame({'计数': [len(df)]})

        # 列名简化
        if values:
            col_map = {}
            for v in values:
                agg_label = v.get('label', v['column'])
                col_map[(v['column'], v.get('agg','sum'))] = agg_label
            if agg_dict:
                agg_result.columns = [
                    c if isinstance(c, str)
                    else col_map.get(c, f"{c[0]}_{c[1]}")
                    for c in agg_result.columns
                ]

        # 转换数据
        records = json.loads(agg_result.to_json(orient='records', force_ascii=False))
        result_cols = list(agg_result.columns)

        # 生成图表
        charts = self._auto_chart(agg_result, row_dims, values, col_dims)

        return {
            'columns': result_cols,
            'data': records,
            'rows': len(records),
            'charts': charts,
            'dimensions': {
                'row': row_dims,
                'col': col_dims,
                'values': values,
            }
        }

    # ────────────────────────────────────────────
    # 图表自动生成
    # ────────────────────────────────────────────
    def _auto_chart(self, df: pd.DataFrame,
                    row_dims: list,
                    values: list,
                    col_dims: list = None) -> dict:
        charts = {}
        if len(df) == 0:
            return charts

        # 获取分组列名与值列名
        row_col = row_dims[0]['column'] if row_dims else None
        val_col = values[0]['column'] if values else '计数'
        val_label = values[0].get('label', val_col) if values else '计数'
        val_agg = values[0].get('agg', 'sum') if values else 'count'

        if val_col not in df.columns and val_col != '计数':
            return charts

        # 确保数值
        if val_col != '计数':
            df[val_col] = pd.to_numeric(df[val_col], errors='coerce').fillna(0)

        if row_col and row_col in df.columns:
            # 柱状图（行维度 vs 值）
            plot_df = df.sort_values(val_col, ascending=False).head(20)
            names = [str(v)[:15] for v in plot_df[row_col].values]
            vals = plot_df[val_col].values

            if len(names) > 0:
                fig, ax = plt.subplots(figsize=(max(8, len(names)*0.4), 4.5))
                cmap = _color_map(names)
                colors = [cmap[n] for n in names]

                if len(names) <= 8:
                    bars = ax.bar(names, vals, color=colors, width=0.55,
                                  edgecolor='white', linewidth=0.8)
                    for b, v in zip(bars, vals):
                        ax.text(b.get_x() + b.get_width()/2, b.get_height(),
                                f'{v:,.0f}', ha='center', va='bottom',
                                fontsize=9, fontweight='bold', color='#1e293b')
                    plt.setp(ax.get_xticklabels(), rotation=25, ha='right', fontsize=9)
                else:
                    bars = ax.barh(names[::-1], vals[::-1], color=colors[::-1],
                                   height=0.5, edgecolor='white')
                    for b, v in zip(bars, vals[::-1]):
                        ax.text(b.get_width() + max(vals)*0.01, b.get_y() + b.get_height()/2,
                                f'{v:,.0f}', ha='left', va='center', fontsize=8,
                                color='#64748b')

                ax.set_title(f'{val_label} 分析', fontsize=14, fontweight='bold',
                             color='#1e293b', pad=12)
                ax.spines['top'].set_visible(False)
                ax.spines['right'].set_visible(False)
                ax.spines['left'].set_color('#e2e8f0')
                ax.spines['bottom'].set_color('#e2e8f0')
                ax.tick_params(colors='#64748b', labelsize=9)
                charts['main'] = self._save_chart(fig, 'main')

            # 饼图（占比，最多10个）
            if len(names) <= 12:
                fig2, ax2 = plt.subplots(figsize=(7, 5))
                total = sum(vals)
                labels_pie = [f'{n}  {v/total*100:.1f}%' for n, v in zip(names[:10], vals[:10])]
                if len(vals) > 10:
                    other = sum(vals[10:])
                    labels_pie.append(f'其他  {other/total*100:.1f}%')
                    vals_pie = list(vals[:10]) + [other]
                else:
                    vals_pie = list(vals[:10])
                cmap_pie = _color_map(labels_pie)
                colors_pie = [cmap_pie[l] for l in labels_pie]
                ax2.pie(vals_pie, labels=labels_pie, colors=colors_pie,
                        startangle=90, counterclock=False,
                        wedgeprops={'edgecolor': 'white', 'linewidth': 2},
                        textprops={'fontsize': 11, 'color': '#1e293b'})
                ax2.set_title(f'{val_label} 占比', fontsize=15, fontweight='bold',
                              color='#1e293b', pad=15)
                charts['pie'] = self._save_chart(fig2, 'pie')

        return charts

    def _save_chart(self, fig, name):
        path = os.path.join(self.chart_dir, f'{name}.png')
        fig.savefig(path, dpi=180, bbox_inches='tight', facecolor='white',
                    edgecolor='none')
        plt.close(fig)
        with open(path, 'rb') as f:
            b64 = base64.b64encode(f.read()).decode()
        return f'data:image/png;base64,{b64}'

    # ────────────────────────────────────────────
    # 报告生成
    # ────────────────────────────────────────────
    def build_html_report(self, title: str, aggr_result: dict,
                          join_info: list = None, org_id: str = 'default') -> str:
        """生成HTML报告"""
        dims = aggr_result.get('dimensions', {})
        charts = aggr_result.get('charts', {})
        data = aggr_result.get('data', [])
        cols = aggr_result.get('columns', [])

        row_label = dims['row'][0]['label'] if dims.get('row') else '维度'
        val_label = dims['values'][0].get('label', dims['values'][0]['column']) if dims.get('values') else '数值'
        val_agg = dims['values'][0].get('agg', 'sum') if dims.get('values') else '计数'
        agg_label = {'sum':'求和','avg':'平均','count':'计数','min':'最小值','max':'最大值'}.get(val_agg, val_agg)
        total_val = sum(r.get(cols[-1], 0) for r in data) if data and len(cols) > 1 else 0

        # 表格行
        table_rows = ''
        for i, r in enumerate(data):
            bg = '#F8FAFC' if i % 2 == 0 else '#FFFFFF'
            cells = ''.join(f'<td style="padding:6px 10px;font-size:12px;text-align:{"right" if c == cols[-1] else "left"}">'
                           f'{r.get(c, "")}</td>' for c in cols[:6])  # 最多6列
            table_rows += f'<tr style="background:{bg}">{cells}</tr>'

        report_id = hashlib.md5(f"{org_id}{datetime.now().timestamp()}".encode()).hexdigest()[:12]

        html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
  *,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Noto Sans SC","PingFang SC","Microsoft YaHei",sans-serif;background:#F1F5F9;color:#1E293B;line-height:1.6}}
  .header{{background:linear-gradient(135deg,#0F172A 0%,#1E293B 100%);color:#fff;padding:40px 0 36px;border-bottom:4px solid #2563EB}}
  .header .inner{{max-width:1100px;margin:0 auto;padding:0 32px}}
  .header h1{{font-size:26px;font-weight:700;margin-bottom:4px}}
  .header .sub{{color:#94A3B8;font-size:14px}}
  .header .meta{{color:#64748B;font-size:12px;margin-top:10px;display:flex;gap:20px}}
  .kpi-row{{max-width:1100px;margin:-24px auto 0;padding:0 32px;display:grid;grid-template-columns:repeat(auto-fit, minmax(200px,1fr));gap:12px;position:relative;z-index:10}}
  .kpi-card{{background:#fff;border-radius:10px;padding:16px 20px;box-shadow:0 1px 3px rgba(0,0,0,.06);border-top:3px solid #2563EB}}
  .kpi-card .label{{font-size:11px;color:#64748B;margin-bottom:3px}}
  .kpi-card .value{{font-size:22px;font-weight:700;color:#1E293B}}
  .container{{max-width:1100px;margin:0 auto;padding:0 32px}}
  .section{{margin-top:28px}}
  .section-title{{font-size:17px;font-weight:700;color:#1E293B;padding-bottom:8px;border-bottom:2px solid #E2E8F0;margin-bottom:16px;display:flex;align-items:center;gap:10px}}
  .section-title .badge{{font-size:10px;font-weight:500;padding:2px 10px;border-radius:20px;background:#DBEAFE;color:#2563EB}}
  .card{{background:#fff;border-radius:10px;box-shadow:0 1px 3px rgba(0,0,0,.05);overflow:hidden}}
  .card .body{{padding:18px}}
  .card img{{width:100%;height:auto;display:block}}
  .data-table{{width:100%;border-collapse:collapse}}
  .data-table th{{background:#1E293B;color:#fff;font-size:11px;font-weight:600;padding:8px 10px;text-align:left;white-space:nowrap}}
  .data-table tr:hover{{background:#F1F5F9!important}}
  .full-card{{background:#fff;border-radius:10px;box-shadow:0 1px 3px rgba(0,0,0,.05);padding:22px}}
  .dim-tag{{display:inline-block;padding:2px 10px;border-radius:12px;font-size:11px;font-weight:500;margin:2px}}
  .dim-tag.row{{background:#DBEAFE;color:#2563EB}}
  .dim-tag.val{{background:#DCFCE7;color:#16A34A}}
  .dim-tag.agg{{background:#FEF3C7;color:#D97706}}
  .footer{{text-align:center;padding:28px;color:#94A3B8;font-size:11px;margin-top:36px;border-top:1px solid #E2E8F0}}
  @media(max-width:768px){{.kpi-row{{grid-template-columns:1fr 1fr}}}}
</style></head>
<body>
<div class="header">
  <div class="inner">
    <h1>📊 {title}</h1>
    <div class="meta">
      <span>📅 {datetime.now().strftime("%Y年%m月%d日")}</span>
      <span>🔬 纯本地运算 · 数据安全</span>
    </div>
  </div>
</div>

<div class="kpi-row">
  <div class="kpi-card"><div class="label">行维度</div><div class="value">{row_label}<span class="dim-tag row">分组</span></div></div>
  <div class="kpi-card"><div class="label">聚合指标</div><div class="value">{val_label}<span class="dim-tag val">数值</span></div></div>
  <div class="kpi-card"><div class="label">聚合方式</div><div class="value">{agg_label}<span class="dim-tag agg">运算</span></div></div>
  <div class="kpi-card"><div class="label">数据行数</div><div class="value">{len(data)}<span style="font-size:12px;color:#94a3b8;font-weight:400"> 条</span></div></div>
</div>

<div class="container">
  <div class="section">
    <div class="section-title">📈 分析图表 <span class="badge">{row_label} × {val_label}</span></div>'''

        if 'main' in charts:
            html += f'<div class="card"><div class="body"><img src="{charts["main"]}" alt="分析图表"></div></div>'
        if 'pie' in charts:
            html += f'<div style="margin-top:18px" class="card"><div class="body"><img src="{charts["pie"]}" alt="占比图"></div></div>'

        html += f'''
  </div>

  <div class="section">
    <div class="section-title">📋 明细数据 <span class="badge">{len(data)}行</span></div>
    <div class="full-card">'''
        if data:
            html += '<table class="data-table"><thead><tr>'
            for c in cols[:6]:
                html += f'<th>{" " if c == cols[-1] else ""}{c}</th>'
            html += '</tr></thead><tbody>' + table_rows + '</tbody></table>'
        else:
            html += '<p style="color:#94a3b8;font-size:13px;text-align:center;padding:20px">暂无数据</p>'

        html += '''
    </div>
  </div>
</div>

<div class="footer">
  百应智星 · 经营分析 V2 · 纯本地运算
</div>
</body>
</html>'''
        return html, report_id

    def cleanup(self):
        """清理临时文件"""
        import shutil
        if os.path.exists(self.work_dir):
            shutil.rmtree(self.work_dir, ignore_errors=True)
