"""PDF business report (reportlab platypus) with a revenue chart."""
from __future__ import annotations

from io import BytesIO

from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

INK = colors.HexColor('#1C2433')
MUTED = colors.HexColor('#5A6478')
TEAL = colors.HexColor('#0E7C7B')
AMBER = colors.HexColor('#B7791F')
RED = colors.HexColor('#B42318')
GRID = colors.HexColor('#E3E7EE')
SURFACE = colors.HexColor('#F3F5F8')


def _styles():
    base = getSampleStyleSheet()
    return {
        'title': ParagraphStyle('t', parent=base['Title'], textColor=INK, alignment=0, fontSize=22, spaceAfter=4),
        'sub': ParagraphStyle('s', parent=base['Normal'], textColor=MUTED, fontSize=9.5, spaceAfter=10),
        'h2': ParagraphStyle('h', parent=base['Heading2'], textColor=INK, fontSize=13, spaceBefore=12, spaceAfter=6),
        'body': ParagraphStyle('b', parent=base['Normal'], textColor=INK, fontSize=9.5, leading=13),
        'note': ParagraphStyle('n', parent=base['Normal'], textColor=MUTED, fontSize=8.5, leading=11),
    }


def _money(v):
    return '–' if v is None else f'${float(v):,.0f}'


def _pct(v):
    return '–' if v is None else f'{float(v):+.1f}%'


def _table(rows, widths, align_right_from=1):
    t = Table(rows, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', 8.5), ('FONT', (0, 1), (-1, -1), 'Helvetica', 8.5),
        ('TEXTCOLOR', (0, 0), (-1, 0), MUTED), ('TEXTCOLOR', (0, 1), (-1, -1), INK),
        ('LINEBELOW', (0, 0), (-1, 0), 0.8, INK), ('LINEBELOW', (0, 1), (-1, -1), 0.3, GRID),
        ('ALIGN', (align_right_from, 0), (-1, -1), 'RIGHT'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    return t


def _kpi_block(kpis, growth):
    cells = [('GMV', _money(kpis['gmv'])), ('Orders', f"{kpis['orders']:,}"),
             ('Avg order value', _money(kpis['average_order_value'])), ('Customers', f"{kpis['customers']:,}"),
             ('Last 30 days', _money(growth['last_30_days_gmv'])), ('vs previous 30', _pct(growth['growth_30d_pct'])),
             ('Low stock', str(kpis['low_stock_products'])), ('Out of stock', str(kpis['out_of_stock_products']))]
    label = ParagraphStyle('l', fontName='Helvetica', fontSize=8, textColor=MUTED)
    value = ParagraphStyle('v', fontName='Helvetica-Bold', fontSize=14, textColor=INK, leading=17)
    grid = [[Paragraph(lbl, label) for lbl, _ in cells[:4]], [Paragraph(v, value) for _, v in cells[:4]],
            [Paragraph(lbl, label) for lbl, _ in cells[4:]], [Paragraph(v, value) for _, v in cells[4:]]]
    t = Table(grid, colWidths=[44 * mm] * 4)
    t.setStyle(TableStyle([('LINEBELOW', (0, 1), (-1, 1), 0.3, GRID), ('BOTTOMPADDING', (0, 1), (-1, 1), 8),
                           ('TOPPADDING', (0, 2), (-1, 2), 8), ('LEFTPADDING', (0, 0), (-1, -1), 0)]))
    return t


def _revenue_chart(monthly):
    months = monthly[-12:]
    d = Drawing(176 * mm, 62 * mm)
    if not months:
        return d
    chart = VerticalBarChart()
    chart.x, chart.y, chart.width, chart.height = 14 * mm, 10 * mm, 158 * mm, 46 * mm
    chart.data = [[m['gmv'] for m in months]]
    chart.categoryAxis.categoryNames = [m['period'][2:] for m in months]
    chart.categoryAxis.labels.fontSize = 7
    chart.categoryAxis.labels.fillColor = MUTED
    chart.valueAxis.labels.fontSize = 7
    chart.valueAxis.labels.fillColor = MUTED
    chart.valueAxis.labelTextFormat = lambda v: f'{v / 1000:,.0f}k' if v >= 1000 else f'{v:,.0f}'
    chart.valueAxis.valueMin = 0
    chart.valueAxis.gridStrokeColor = GRID
    chart.valueAxis.visibleGrid = True
    chart.bars[0].fillColor = TEAL
    chart.bars[0].strokeColor = None
    chart.barSpacing = 2
    d.add(chart)
    d.add(String(14 * mm, 58 * mm, 'GMV by month', fontName='Helvetica-Bold', fontSize=8.5, fillColor=INK))
    return d


def build_pdf(data: dict) -> bytes:
    s = _styles()
    out = BytesIO()
    doc = SimpleDocTemplate(out, pagesize=A4, leftMargin=17 * mm, rightMargin=17 * mm, topMargin=16 * mm,
                            bottomMargin=16 * mm, title='ShopSense business report', author='ShopSense')
    story = [Paragraph('ShopSense business report', s['title']),
             Paragraph(f"{data['scope']} · generated {data['generated_at']}", s['sub']),
             _kpi_block(data['kpis'], data['revenue']['growth']), Spacer(1, 6),
             _revenue_chart(data['revenue']['monthly'])]

    cats = data['revenue']['categories'][:8]
    if cats:
        story += [Paragraph('Category mix, last 90 days', s['h2']),
                  _table([['Category', 'GMV', 'Share', 'Growth']] +
                         [[c['category'], _money(c['gmv']), f"{c['share_pct']}%", _pct(c['growth_pct'])] for c in cats],
                         [70 * mm, 36 * mm, 30 * mm, 30 * mm])]

    b = data['benchmark']
    story.append(Paragraph('Vendor benchmarking, last 90 days', s['h2']))
    if data['vendor_id'] is None:
        story.append(_table([['#', 'Vendor', 'GMV', 'Share', 'Growth', 'AOV', 'Score']] +
                            [[v['rank'], v['vendor'], _money(v['gmv']), f"{v['share_pct']}%", _pct(v['growth_pct']),
                              _money(v['aov']), f"{v['score']:.0f}"] for v in b['vendors']],
                            [10 * mm, 52 * mm, 28 * mm, 18 * mm, 20 * mm, 22 * mm, 16 * mm], align_right_from=2))
    else:
        you, m = b.get('you') or {}, b['marketplace']
        story.append(_table([['Measure', 'You', 'Marketplace median'],
                             ['GMV', _money(you.get('gmv')), _money(m.get('median_gmv'))],
                             ['Growth', _pct(you.get('growth_pct')), _pct(m.get('median_growth_pct'))],
                             ['Average order value', _money(you.get('aov')), _money(m.get('median_aov'))],
                             ['Rank', f"{you.get('rank', '–')} of {m.get('vendors', '–')}", '']],
                            [60 * mm, 50 * mm, 56 * mm]))

    ci = data['customers']
    if ci.get('available'):
        rc = ci['risk_counts']
        story += [Paragraph('Customer intelligence', s['h2']),
                  Paragraph(f"{ci['customers']:,} customers scored for churn risk: <b>{rc.get('High', 0)}</b> high, "
                            f"{rc.get('Medium', 0)} medium, {rc.get('Low', 0)} low. Model ROC AUC "
                            f"{ci['model_metrics']['roc_auc']:.2f} on the latest 90-day window "
                            f"(recency-only baseline {ci['model_metrics']['baseline_recency_auc']:.2f}).", s['body'])]
        if ci['by_segment']:
            story.append(Spacer(1, 4))
            story.append(_table([['Segment', 'Customers', 'Avg churn risk', 'Expected value, 12 months']] +
                                [[x['segment'], f"{x['customers']:,}", f"{x['avg_churn']:.0%}", _money(x['value_12m'])]
                                 for x in ci['by_segment']], [50 * mm, 30 * mm, 36 * mm, 50 * mm]))

    picks = [(sg['segment'], p) for sg in data['segment_recommendations'] for p in sg['recommendations'][:1]]
    if picks:
        story += [Paragraph('What to promote to each segment', s['h2']),
                  _table([['Segment', 'Product', 'Lift']] + [[sg, p['product'], f"{p['lift']:.2f}×"] for sg, p in picks],
                         [50 * mm, 90 * mm, 26 * mm])]

    short = [p for p in data['forecast']['products'] if p['shortfall'] > 0][:10]
    story.append(Paragraph(f"Stock that will not last {data['forecast']['weeks']} weeks", s['h2']))
    if short:
        story.append(_table([['Product', 'In stock', 'Forecast demand', 'Shortfall']] +
                            [[p['name'], p['current_stock'], f"{p['forecast_units']:.0f}", f"{p['shortfall']:.0f}"]
                             for p in short], [76 * mm, 28 * mm, 34 * mm, 28 * mm]))
    else:
        story.append(Paragraph('Every product has enough stock for the forecast period.', s['body']))
    story += [Spacer(1, 10), Paragraph(f"Forecast source: {data['forecast']['source']}. GMV is item value on placed "
                                       'orders, not collected payment or profit. Demo currency.', s['note'])]
    doc.build(story)
    return out.getvalue()
