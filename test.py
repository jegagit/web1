from nicegui import ui
import csv
import os
import re
from dataclasses import dataclass
import nicegui

print(nicegui.version)

CSV_FILE = '/Users/jra/working/vscode/pyprojects/nicegui-market-simulator/src/data/ES250930.csv'
ISSUE_COL = 'Issues'
YIELD_COL = 'Average Simple Yield'

TBILL_PATTERN = re.compile(r'^T-BILL(\d+)$')
JGB_PATTERN = re.compile(r'^JGB(\d+)\((\d+)\)$')
JBI_PATTERN = re.compile(r'^JGB I/L(\d+)$')

JGB_TERM_MAP = {'2': 'JN', '5': 'JS', '10': 'JB', '20': 'JL', '30': 'JX', '40': 'JU'}

@dataclass
class Issue:
    ticker: str
    raw: str
    closing_yield: float | None = None

def parse_issue(name: str) -> Issue | None:
    if not isinstance(name, str):
        return None
    if m := TBILL_PATTERN.match(name):
        return Issue(ticker='JT' + m.group(1), raw=name)
    if m := JGB_PATTERN.match(name):
        prefix = JGB_TERM_MAP.get(m.group(2), 'JGB')
        return Issue(ticker=f'{prefix}{m.group(1)}', raw=name)
    if m := JBI_PATTERN.match(name):
        return Issue(ticker='JBI' + m.group(1), raw=name)
    return None

def load_csv(path: str) -> dict[str, Issue]:
    """Load CSV and return {ticker: Issue} mapping."""
    if not os.path.exists(path):
        return {}
    encodings = ['utf-8-sig', 'utf-8', 'shift_jis', 'cp932', 'sjis', 'euc_jp', 'iso2022_jp']
    
    for enc in encodings:
        try:
            with open(path, newline='', encoding=enc, errors='strict') as f:
                reader = csv.DictReader(f)
                issues = {}
                for row in reader:
                    raw_issue = row.get(ISSUE_COL)
                    if not raw_issue:
                        continue
                    issue = parse_issue(raw_issue)
                    if not issue:
                        continue
                    
                    val = row.get(YIELD_COL)
                    if val:
                        try:
                            issue.closing_yield = float(val)
                        except ValueError:
                            pass
                    
                    issues[issue.ticker] = issue
                print(f'Loaded CSV ({enc}) issues={len(issues)}')
                return issues
        except UnicodeDecodeError:
            continue
    
    print(f'Failed to decode CSV')
    return {}

class TradeManager:
    def __init__(self):
        self.trades = []
        self.next_id = 1
        self.selected = set()
    
    def add(self, issue: str, closing_yield: float, trade_yield: float, spread_bp: float, quantity: float):
        trade = {
            'id': self.next_id,
            'issue': issue,
            'closing_yield': closing_yield,
            'trade_yield': trade_yield,
            'spread_bp': spread_bp,
            'quantity': quantity,
        }
        self.trades.append(trade)
        self.next_id += 1
        return trade
    
    def remove_selected(self):
        if not self.selected:
            return
        self.trades = [t for t in self.trades if t['id'] not in self.selected]
        self.selected.clear()
    
    def update_selection(self, rows):
        self.selected = {r['id'] for r in rows if 'id' in r}

def build_ui(issues: dict[str, Issue]):
    if not issues:
        ui.label('No issues loaded')
        return
    
    trade_mgr = TradeManager()
    ticker_list = sorted(issues.keys())
    def on_issue_change():
        # This handler now takes no arguments and reads the value directly
        ticker = issue_sel.value
        print(f'DEBUG: Issue changed to -> {ticker}') # Add debug print
        issue = issues.get(ticker)
        if issue and issue.closing_yield is not None:
            closing_yield.value = round(issue.closing_yield, 6)
            recalc_yield_from_spread()
        status.text = f'Selected: {ticker}'
        status.update() 

    # Inputs
    with ui.row().classes('items-end gap-4'):
        issue_sel = ui.select(ticker_list, label='Issue', value=ticker_list[0], with_input=True, on_change=on_issue_change)
        closing_yield = ui.number(label='JSDA Yield', value=0.0, step=0.0001)
        spread = ui.number(label='Spread (bp)', value=0.0, step=0.01)
        trade_yield = ui.number(label='Trade Yield', value=0.0, step=0.0001)
        quantity = ui.number(label='Quantity', value=0.0001, step=0.0001, min=0.0001)
        add_btn = ui.button('Add')
    
    status = ui.label('Ready')
    
    # Trade table with action column
    columns = [
        {'name': 'issue', 'label': 'Issue', 'field': 'issue'},
        {'name': 'closing_yield', 'label': 'JSDA Close', 'field': 'closing_yield'},
        {'name': 'trade_yield', 'label': 'Trade Yield', 'field': 'trade_yield'},
        {'name': 'spread_bp', 'label': 'Spread (bp)', 'field': 'spread_bp'},
        {'name': 'quantity', 'label': 'Quantity', 'field': 'quantity'},
        {'name': 'actions', 'label': 'Actions', 'field': 'actions'},
    ]
    
    table = ui.table(columns=columns, rows=trade_mgr.trades, row_key='id').classes('w-full mt-4')
    
    # Add slot for action buttons in each row
    table.add_slot('body-cell-actions', '''
        <q-td :props="props">
            <q-btn flat dense icon="delete" color="negative" 
                   @click="$parent.$emit('delete_row', props.row.id)" />
        </q-td>
    ''')
    
    def delete_row(e):
        row_id = e.args
        trade_mgr.trades = [t for t in trade_mgr.trades if t['id'] != row_id]
        table.rows = trade_mgr.trades
        table.update()
        status.text = f'Deleted trade {row_id}'
    
    table.on('delete_row', delete_row)
    
    # Handlers
    def recalc_yield_from_spread():
        cy = float(closing_yield.value or 0)
        sp = float(spread.value or 0)
        trade_yield.value = round(cy + sp / 100.0, 6)
    
    def recalc_spread_from_yield():
        cy = float(closing_yield.value or 0)
        ty = float(trade_yield.value or 0)
        spread.value = round((ty - cy) * 100.0, 4)
    
    def on_add():
        trade_mgr.add(
            issue_sel.value,
            closing_yield.value,
            trade_yield.value,
            spread.value,
            quantity.value
        )
        table.rows = trade_mgr.trades
        table.update()
        status.text = f'Added {issue_sel.value}'
    
    # Wire events
    issue_sel.on('change', on_issue_change)
    spread.on('change', recalc_yield_from_spread)
    trade_yield.on('change', recalc_spread_from_yield)
    add_btn.on_click(on_add)
    
    # Initialize
    #on_issue_change(issue_sel.value)

issues = load_csv(CSV_FILE)
build_ui(issues)
ui.run()