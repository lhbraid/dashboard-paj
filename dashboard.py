# -*- coding: utf-8 -*-
import dash
from dash import dcc, html, Input, Output, State, dash_table
import dash_bootstrap_components as dbc
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import numpy as np
import io
import base64
from datetime import datetime
import weasyprint
import os
import uuid # Para nomes de arquivos temporários

# --- Constantes e Configurações Iniciais ---
UPLOAD_DIR = "/home/ubuntu/upload"
ASSETS_DIR = "/home/ubuntu/dashboard_dpu/assets"
LOGO_PATH = f"{ASSETS_DIR}/logo-dpu.png"
INITIAL_DATA_PATH = "/home/ubuntu/dashboard_dpu/initial_data.xlsx"
TEMP_DIR = "/tmp" # Diretório para imagens temporárias

# Colunas esperadas e renomeação
COLUMN_MAPPING = {
    'Oficio': 'Ofício',
    'Data da instauração': 'Data da Instauração',
    'Materia': 'Matéria'
}
REQUIRED_COLUMNS = ['PAJ', 'Unidade', 'Assistido', 'Ofício', 'Pretensão', 'Data da Instauração', 'Matéria', 'Atribuição', 'Defensor', 'Usuário']
DATE_COLUMN = 'Data da Instauração'

# --- Funções Auxiliares ---
def load_data(file_path):
    """Carrega dados de um arquivo Excel, renomeia colunas e trata datas."""
    try:
        df = pd.read_excel(file_path)
        df.rename(columns=COLUMN_MAPPING, inplace=True)

        # Verificar se todas as colunas necessárias existem após renomear
        missing_cols = [col for col in REQUIRED_COLUMNS if col not in df.columns]
        if missing_cols:
            raise ValueError(f"Colunas ausentes no arquivo: {', '.join(missing_cols)}")

        # Converter coluna de data, tratando erros
        df[DATE_COLUMN] = pd.to_datetime(df[DATE_COLUMN], errors='coerce')
        df.dropna(subset=[DATE_COLUMN], inplace=True) # Remover linhas onde a data não pôde ser convertida

        # Extrair ano e mês para filtros e gráficos
        df['Ano'] = df[DATE_COLUMN].dt.year
        df['Mês'] = df[DATE_COLUMN].dt.month
        # Criar AnoMês como string para serialização JSON
        df['AnoMês'] = df[DATE_COLUMN].dt.to_period('M').astype(str)

        return df
    except FileNotFoundError:
        print(f"Erro: Arquivo inicial não encontrado em {file_path}")
        return pd.DataFrame(columns=REQUIRED_COLUMNS + ['Ano', 'Mês', 'AnoMês'])
    except ValueError as ve:
        print(f"Erro de valor ao carregar dados: {ve}")
        return pd.DataFrame(columns=REQUIRED_COLUMNS + ['Ano', 'Mês', 'AnoMês'])
    except Exception as e:
        print(f"Erro inesperado ao carregar dados de {file_path}: {e}")
        return pd.DataFrame(columns=REQUIRED_COLUMNS + ['Ano', 'Mês', 'AnoMês'])

def parse_contents(contents, filename):
    """Processa o conteúdo do arquivo carregado."""
    content_type, content_string = contents.split(',')
    decoded = base64.b64decode(content_string)
    try:
        if 'xls' in filename:
            df = pd.read_excel(io.BytesIO(decoded))
            df.rename(columns=COLUMN_MAPPING, inplace=True)
            missing_cols = [col for col in REQUIRED_COLUMNS if col not in df.columns]
            if missing_cols:
                 raise ValueError(f"Colunas ausentes no arquivo carregado: {', '.join(missing_cols)}")
            df[DATE_COLUMN] = pd.to_datetime(df[DATE_COLUMN], errors='coerce')
            df.dropna(subset=[DATE_COLUMN], inplace=True)
            df['Ano'] = df[DATE_COLUMN].dt.year
            df['Mês'] = df[DATE_COLUMN].dt.month
            # Criar AnoMês como string para serialização JSON
            df['AnoMês'] = df[DATE_COLUMN].dt.to_period('M').astype(str)
            return df
        else:
            raise ValueError("Formato de arquivo não suportado. Use .xlsx ou .xls")
    except Exception as e:
        print(f"Erro ao processar o arquivo carregado {filename}: {e}")
        return None

def generate_report_html_base64(dff, top_n):
    """Gera o conteúdo HTML para o relatório PDF com base nos dados filtrados (com imagens base64)."""
    if dff.empty:
        return "<h1>Relatório DPU</h1><p>Nenhum dado corresponde aos filtros selecionados.</p>"

    total_pajs = len(dff)
    materia_counts = dff['Matéria'].value_counts()
    fig_materia = px.pie(materia_counts, values=materia_counts.values, names=materia_counts.index, title="Distribuição por Matéria", hole=.4, color_discrete_sequence=px.colors.qualitative.Pastel)
    fig_materia.update_traces(textinfo='percent+label', pull=[0.05] * len(materia_counts))
    fig_materia.update_layout(showlegend=False, margin=dict(t=50, b=0, l=0, r=0))

    oficio_counts = dff['Ofício'].value_counts()
    fig_oficio = px.pie(oficio_counts, values=oficio_counts.values, names=oficio_counts.index, title="Distribuição por Ofício", hole=.4, color_discrete_sequence=px.colors.qualitative.Set2)
    fig_oficio.update_traces(textinfo='percent+label', pull=[0.05] * len(oficio_counts))
    fig_oficio.update_layout(showlegend=False, margin=dict(t=50, b=0, l=0, r=0))

    user_counts = dff['Usuário'].value_counts().nlargest(top_n)
    fig_usuarios = px.bar(user_counts, x=user_counts.index, y=user_counts.values, text_auto=True, title=f"TOP {top_n} Usuários por Nº de PAJs", labels={'x': 'Usuário', 'y': 'Nº PAJs'}, color_discrete_sequence=px.colors.qualitative.Vivid)
    fig_usuarios.update_layout(xaxis_tickangle=-45, margin=dict(t=50, b=100, l=0, r=0))

    # AnoMês já é string, o groupby funciona
    evolucao = dff.groupby('AnoMês').size().reset_index(name='Contagem')
    # Ordenar pela string AnoMês para garantir ordem cronológica no gráfico
    evolucao = evolucao.sort_values('AnoMês')
    fig_evolucao = px.line(evolucao, x='AnoMês', y='Contagem', markers=True, title="Evolução Mensal de PAJs", labels={'AnoMês': 'Mês/Ano', 'Contagem': 'Nº PAJs'})
    fig_evolucao.update_layout(margin=dict(t=50, b=0, l=0, r=0))

    top10_users_stats = dff['Usuário'].value_counts().nlargest(10).reset_index()
    top10_users_stats.columns = ['Usuário', 'Quantidade PAJs']
    tabela_html = top10_users_stats.to_html(index=False, classes='table table-striped', border=0)

    img_base64 = {}
    figs = {'materia': fig_materia, 'oficio': fig_oficio, 'usuarios': fig_usuarios, 'evolucao': fig_evolucao}
    for name, fig in figs.items():
        try:
            img_bytes = fig.to_image(format="png", scale=2)
            img_base64[name] = base64.b64encode(img_bytes).decode()
        except Exception as e:
            print(f"Erro ao gerar imagem base64 {name}: {e}")
            img_base64[name] = None

    encoded_logo = base64.b64encode(open(LOGO_PATH, 'rb').read()).decode()

    html_string = f"""
    <!DOCTYPE html>
    <html><head><meta charset="UTF-8"><title>Relatório DPU - Visão Geral SIS</title>
    <style>
        body {{ font-family: sans-serif; margin: 20px; }}
        h1, h2, h3 {{ color: #004080; }}
        .chart-container {{ display: flex; flex-wrap: wrap; gap: 20px; margin-bottom: 30px; page-break-inside: avoid; }}
        .chart {{ flex: 1 1 45%; min-width: 300px; border: 1px solid #ccc; padding: 10px; box-shadow: 2px 2px 5px #eee; text-align: center; }}
        .chart img {{ max-width: 100%; height: auto; }}
        .full-width-chart {{ flex: 1 1 100%; }}
        .table-container {{ margin-top: 30px; page-break-inside: avoid; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f2f2f2; }}
        .total-box {{ background-color: #e7f3ff; border-left: 6px solid #2196F3; padding: 15px; margin-bottom: 20px; font-size: 1.2em; }}
        @media print {{ body {{ margin: 0.5cm; }} .chart-container, .table-container {{ page-break-inside: avoid; }} }}
    </style></head><body>
    <h1><img src="data:image/png;base64,{encoded_logo}" height="40px" style="vertical-align: middle; margin-right: 10px;">Relatório DPU - Visão Geral SIS</h1>
    <p>Relatório gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}</p>
    <div class="total-box"><strong>Total PAJs Instaurados (Filtro Aplicado): {total_pajs}</strong></div>
    <div class="chart-container">
        <div class="chart"><h2>Distribuição por Matéria</h2>{'<img src="data:image/png;base64,' + img_base64['materia'] + '">' if img_base64.get('materia') else '<p>Erro.</p>'}</div>
        <div class="chart"><h2>Distribuição por Ofício</h2>{'<img src="data:image/png;base64,' + img_base64['oficio'] + '">' if img_base64.get('oficio') else '<p>Erro.</p>'}</div>
    </div>
    <div class="chart-container"><div class="chart full-width-chart"><h2>TOP {top_n} Usuários por Nº de PAJs</h2>{'<img src="data:image/png;base64,' + img_base64['usuarios'] + '">' if img_base64.get('usuarios') else '<p>Erro.</p>'}</div></div>
    <div class="chart-container"><div class="chart full-width-chart"><h2>Evolução Mensal de PAJs</h2>{'<img src="data:image/png;base64,' + img_base64['evolucao'] + '">' if img_base64.get('evolucao') else '<p>Erro.</p>'}</div></div>
    <div class="table-container"><h2>Detalhes TOP 10 Usuários</h2>{tabela_html}</div>
    </body></html>
    """
    return html_string

# --- Inicialização do App Dash ---
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP], suppress_callback_exceptions=True, assets_folder=ASSETS_DIR)
server = app.server # Necessário para Render

# --- Carregamento Inicial dos Dados ---
df_inicial = load_data(INITIAL_DATA_PATH)

# --- Layout do Dashboard ---
app.layout = dbc.Container(
    [
        # Armazenar dados como string JSON para evitar problemas de serialização
        dcc.Store(id='stored-data', data=df_inicial.to_json(date_format='iso', orient='split') if not df_inicial.empty else None),
        # Cabeçalho
        dbc.Row(
            [
                dbc.Col(html.Img(src=app.get_asset_url('logo-dpu.png'), height="60px"), width="auto"),
                dbc.Col(html.H2("Visão geral do SIS - DAT", className="ms-2"), width=True),
            ],
            align="center",
            className="mb-4 mt-4"
        ),

        # Área de Upload e Filtros
        dbc.Row(
            dbc.Col(
                dbc.Card(
                    dbc.CardBody(
                        [
                            dbc.Row([
                                # Upload
                                dbc.Col([
                                    html.Div("Atualizar Dados:"),
                                    dcc.Upload(
                                        id='upload-data',
                                        children=html.Div([
                                            'Arraste e solte ou ', html.A('Selecione um Arquivo Excel')
                                        ]),
                                        style={
                                            'width': '100%', 'height': '60px', 'lineHeight': '60px',
                                            'borderWidth': '1px', 'borderStyle': 'dashed',
                                            'borderRadius': '5px', 'textAlign': 'center', 'margin': '10px 0px'
                                        },
                                        multiple=False # Aceita apenas um arquivo
                                    ),
                                    html.Div(id='output-data-upload-status')
                                ], width=12, lg=3, className="mb-3 mb-lg-0"),

                                # Filtros
                                dbc.Col([
                                    html.Div("Filtros:"),
                                    dbc.Row([
                                        dbc.Col(dcc.Dropdown(id='filtro-materia', placeholder="Matéria", multi=True), width=6, md=3),
                                        dbc.Col(dcc.Dropdown(id='filtro-oficio', placeholder="Ofício", multi=True), width=6, md=3),
                                        dbc.Col(dcc.Dropdown(id='filtro-usuario', placeholder="Usuário", multi=True), width=6, md=3),
                                        dbc.Col(dcc.DatePickerRange(
                                            id='filtro-data',
                                            display_format='DD/MM/YYYY',
                                            start_date_placeholder_text="Data Início",
                                            end_date_placeholder_text="Data Fim",
                                            clearable=True,
                                        ), width=6, md=3)
                                    ])
                                ], width=12, lg=9)
                            ])
                        ]
                    )
                ), width=12
            ),
            className="mb-4"
        ),

        # Indicadores e Gráficos Principais
        dbc.Row(
            [
                dbc.Col(dbc.Card(dbc.CardBody(id='total-pajs')), width=12, lg=3, className="mb-3"),
                dbc.Col(dbc.Card(dbc.CardBody(dcc.Graph(id='grafico-materia'))), width=12, md=6, lg=4, className="mb-3"),
                dbc.Col(dbc.Card(dbc.CardBody(dcc.Graph(id='grafico-oficio'))), width=12, md=6, lg=5, className="mb-3"),
            ],
            className="mb-4"
        ),

        # Gráficos de Usuários e Evolução Temporal
        dbc.Row(
            [
                dbc.Col(
                    dbc.Card(dbc.CardBody([
                        dbc.Row([
                           dbc.Col(html.H5("PAJs por Usuário"), width=8),
                           dbc.Col(dcc.Dropdown(id='top-n-usuarios', options=[
                               {'label': 'TOP 10', 'value': 10},
                               {'label': 'TOP 20', 'value': 20},
                               {'label': 'TOP 30', 'value': 30},
                               {'label': 'TOP 50', 'value': 50}
                           ], value=10, clearable=False), width=4)
                        ], align="center"),
                        dcc.Graph(id='grafico-usuarios')
                    ])),
                    width=12, lg=7, className="mb-3"
                ),
                dbc.Col(
                    dbc.Card(dbc.CardBody([
                        html.H5("Evolução de PAJs por Mês"),
                        dcc.Graph(id='grafico-evolucao')
                    ])),
                    width=12, lg=5, className="mb-3"
                ),
            ],
            className="mb-4"
        ),

        # Tabela TOP Usuários e Botão PDF
        dbc.Row(
            [
                dbc.Col(
                    dbc.Card(dbc.CardBody([
                        html.H5("Detalhes TOP 10 Usuários"),
                        html.Div(id='tabela-top-usuarios'),
                        dbc.Button("Gerar PDF", id="btn-pdf", color="primary", className="mt-3"),
                        dcc.Download(id="download-pdf")
                    ])),
                    width=12, className="mb-3"
                )
            ]
        )
    ],
    fluid=True,
    className="dbc"
)

# --- Callbacks ---
@app.callback(
    Output('stored-data', 'data'),
    Output('output-data-upload-status', 'children'),
    Input('upload-data', 'contents'),
    State('upload-data', 'filename')
)
def update_output(contents, filename):
    if contents is not None:
        df_new = parse_contents(contents, filename)
        if df_new is not None and not df_new.empty:
            status_message = html.Div([f'Arquivo "{filename}" carregado com sucesso.'], className="text-success")
            # Armazenar como JSON string
            return df_new.to_json(date_format='iso', orient='split'), status_message
        else:
            status_message = html.Div([f'Falha ao carregar o arquivo "{filename}". Verifique o formato e as colunas.'], className="text-danger")
            return dash.no_update, status_message
    return dash.no_update, ""

@app.callback(
    [
        Output('filtro-materia', 'options'),
        Output('filtro-oficio', 'options'),
        Output('filtro-usuario', 'options'),
        Output('filtro-data', 'min_date_allowed'),
        Output('filtro-data', 'max_date_allowed'),
        Output('filtro-data', 'initial_visible_month'),
    ],
    Input('stored-data', 'data')
)
def update_filter_options(jsonified_data):
    if jsonified_data is None:
        return [], [], [], None, None, None

    # Ler dados do JSON string
    df = pd.read_json(jsonified_data, orient='split')
    if df.empty:
         return [], [], [], None, None, None

    # Converter colunas de data
    df[DATE_COLUMN] = pd.to_datetime(df[DATE_COLUMN])

    materias = sorted(df['Matéria'].unique())
    oficios = sorted(df['Ofício'].unique())
    usuarios = sorted(df['Usuário'].unique())

    min_date = df[DATE_COLUMN].min().date()
    max_date = df[DATE_COLUMN].max().date()

    options_materia = [{'label': i, 'value': i} for i in materias]
    options_oficio = [{'label': i, 'value': i} for i in oficios]
    options_usuario = [{'label': i, 'value': i} for i in usuarios]

    return options_materia, options_oficio, options_usuario, min_date, max_date, min_date

# Callback para atualizar os gráficos e a tabela com base nos filtros
@app.callback(
    [
        Output('total-pajs', 'children'),
        Output('grafico-materia', 'figure'),
        Output('grafico-oficio', 'figure'),
        Output('grafico-usuarios', 'figure'),
        Output('grafico-evolucao', 'figure'),
        Output('tabela-top-usuarios', 'children')
    ],
    [
        Input('stored-data', 'data'),
        Input('filtro-materia', 'value'),
        Input('filtro-oficio', 'value'),
        Input('filtro-usuario', 'value'),
        Input('filtro-data', 'start_date'),
        Input('filtro-data', 'end_date'),
        Input('top-n-usuarios', 'value')
    ]
)
def update_dashboard(jsonified_data, materias_selecionadas, oficios_selecionados, usuarios_selecionados, start_date, end_date, top_n):
    if jsonified_data is None:
        empty_fig = go.Figure().update_layout(template='plotly_white', annotations=[dict(text="Sem dados para exibir", showarrow=False)])
        return "Total PAJs: 0", empty_fig, empty_fig, empty_fig, empty_fig, "Nenhum dado disponível para a tabela."

    # Ler dados do JSON string
    dff = pd.read_json(jsonified_data, orient='split')
    if dff.empty:
        empty_fig = go.Figure().update_layout(template='plotly_white', annotations=[dict(text="Sem dados para exibir", showarrow=False)])
        return "Total PAJs: 0", empty_fig, empty_fig, empty_fig, empty_fig, "Nenhum dado disponível para a tabela."

    # Converter colunas de data
    dff[DATE_COLUMN] = pd.to_datetime(dff[DATE_COLUMN])
    # AnoMês já é string

    # Aplicar filtros
    if materias_selecionadas:
        dff = dff[dff['Matéria'].isin(materias_selecionadas)]
    if oficios_selecionados:
        dff = dff[dff['Ofício'].isin(oficios_selecionados)]
    if usuarios_selecionados:
        dff = dff[dff['Usuário'].isin(usuarios_selecionados)]
    if start_date and end_date:
        dff = dff[(dff[DATE_COLUMN] >= pd.to_datetime(start_date)) & (dff[DATE_COLUMN] <= pd.to_datetime(end_date))]
    elif start_date:
        dff = dff[dff[DATE_COLUMN] >= pd.to_datetime(start_date)]
    elif end_date:
        dff = dff[dff[DATE_COLUMN] <= pd.to_datetime(end_date)]

    if dff.empty:
        empty_fig = go.Figure().update_layout(template='plotly_white', annotations=[dict(text="Nenhum dado corresponde aos filtros", showarrow=False)])
        return "Total PAJs: 0", empty_fig, empty_fig, empty_fig, empty_fig, "Nenhum dado corresponde aos filtros."

    # 1. Total de PAJs
    total_pajs = len(dff)
    card_total_pajs = [
        html.H4("Total PAJs Instaurados"),
        html.H2(f"{total_pajs}", className="text-primary")
    ]

    # 2. Gráfico de Rosca por Matéria
    materia_counts = dff['Matéria'].value_counts()
    fig_materia = px.pie(materia_counts, values=materia_counts.values, names=materia_counts.index,
                         title="Distribuição por Matéria", hole=.4, color_discrete_sequence=px.colors.qualitative.Pastel)
    fig_materia.update_traces(textinfo='percent+label', pull=[0.05] * len(materia_counts))
    fig_materia.update_layout(showlegend=False, margin=dict(t=50, b=0, l=0, r=0))

    # 3. Gráfico de Rosca por Ofício
    oficio_counts = dff['Ofício'].value_counts()
    fig_oficio = px.pie(oficio_counts, values=oficio_counts.values, names=oficio_counts.index,
                        title="Distribuição por Ofício", hole=.4, color_discrete_sequence=px.colors.qualitative.Set2)
    fig_oficio.update_traces(textinfo='percent+label', pull=[0.05] * len(oficio_counts))
    fig_oficio.update_layout(showlegend=False, margin=dict(t=50, b=0, l=0, r=0))

    # 4. Gráfico de Colunas por Usuário (TOP N)
    user_counts = dff['Usuário'].value_counts().nlargest(top_n)
    fig_usuarios = px.bar(user_counts, x=user_counts.index, y=user_counts.values, text_auto=True,
                          title=f"TOP {top_n} Usuários por Nº de PAJs", labels={'x': 'Usuário', 'y': 'Nº PAJs'},
                          color_discrete_sequence=px.colors.qualitative.Vivid)
    fig_usuarios.update_layout(xaxis_tickangle=-45, margin=dict(t=50, b=100, l=0, r=0))

    # 5. Gráfico de Linha - Evolução Temporal
    evolucao = dff.groupby('AnoMês').size().reset_index(name='Contagem')
    evolucao = evolucao.sort_values('AnoMês') # Ordenar por string AnoMês
    fig_evolucao = px.line(evolucao, x='AnoMês', y='Contagem', markers=True,
                           title="Evolução Mensal de PAJs", labels={'AnoMês': 'Mês/Ano', 'Contagem': 'Nº PAJs'})
    fig_evolucao.update_layout(margin=dict(t=50, b=0, l=0, r=0))

    # 6. Tabela TOP 10 Usuários
    top10_users_stats = dff['Usuário'].value_counts().nlargest(10).reset_index()
    top10_users_stats.columns = ['Usuário', 'Quantidade PAJs']
    tabela = dash_table.DataTable(
        columns=[{"name": i, "id": i} for i in top10_users_stats.columns],
        data=top10_users_stats.to_dict('records'),
        style_table={'overflowX': 'auto'},
        style_cell={'textAlign': 'left', 'padding': '5px'},
        style_header={
            'backgroundColor': 'rgb(230, 230, 230)',
            'fontWeight': 'bold'
        },
        style_data_conditional=[
            {
                'if': {'row_index': 'odd'},
                'backgroundColor': 'rgb(248, 248, 248)'
            }
        ]
    )

    return card_total_pajs, fig_materia, fig_oficio, fig_usuarios, fig_evolucao, tabela

# Callback para gerar PDF
@app.callback(
    Output("download-pdf", "data"),
    Input("btn-pdf", "n_clicks"),
    [
        State('stored-data', 'data'),
        State('filtro-materia', 'value'),
        State('filtro-oficio', 'value'),
        State('filtro-usuario', 'value'),
        State('filtro-data', 'start_date'),
        State('filtro-data', 'end_date'),
        State('top-n-usuarios', 'value')
    ],
    prevent_initial_call=True,
)
def generate_pdf(n_clicks, jsonified_data, materias_selecionadas, oficios_selecionados, usuarios_selecionados, start_date, end_date, top_n):
    if not n_clicks or jsonified_data is None:
        return dash.no_update

    # Ler dados do JSON string
    dff = pd.read_json(jsonified_data, orient='split')
    if dff.empty:
        return dash.no_update # Ou gerar um PDF indicando que não há dados

    # Converter colunas de data
    dff[DATE_COLUMN] = pd.to_datetime(dff[DATE_COLUMN])
    # AnoMês já é string

    # Aplicar filtros (mesma lógica do update_dashboard)
    if materias_selecionadas:
        dff = dff[dff['Matéria'].isin(materias_selecionadas)]
    if oficios_selecionados:
        dff = dff[dff['Ofício'].isin(oficios_selecionados)]
    if usuarios_selecionados:
        dff = dff[dff['Usuário'].isin(usuarios_selecionados)]
    if start_date and end_date:
        dff = dff[(dff[DATE_COLUMN] >= pd.to_datetime(start_date)) & (dff[DATE_COLUMN] <= pd.to_datetime(end_date))]
    elif start_date:
        dff = dff[dff[DATE_COLUMN] >= pd.to_datetime(start_date)]
    elif end_date:
        dff = dff[dff[DATE_COLUMN] <= pd.to_datetime(end_date)]

    try:
        # Gerar HTML para o relatório com imagens base64
        html_content_base64 = generate_report_html_base64(dff, top_n)

        # Gerar PDF a partir do HTML usando WeasyPrint
        pdf_bytes = weasyprint.HTML(string=html_content_base64).write_pdf()

        return dcc.send_bytes(pdf_bytes, f"relatorio_dpu_sis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf")

    except Exception as e:
        print(f"Erro ao gerar PDF: {e}")
        return dash.no_update

# --- Execução do App ---
if __name__ == '__main__':
    # Obter a porta da variável de ambiente PORT, com um padrão (ex: 8050)
    port = int(os.environ.get("PORT", 8050))
    # Para desenvolvimento local:
    # app.run(debug=True, host='0.0.0.0', port=port)
    # Para Render/produção (escuta em 0.0.0.0 e porta definida pela variável de ambiente):
    app.run(debug=False, host='0.0.0.0', port=port)

