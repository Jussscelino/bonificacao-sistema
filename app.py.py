import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

# ============================================
# CONFIGURACAO DA PAGINA
# ============================================
st.set_page_config(
    page_title="Sistema de Bonificacao",
    page_icon="🎁",
    layout="wide"
)

# ============================================
# CONSTANTES
# ============================================
TAXA_BONIFICACAO = 0.01
DIAS_VALIDADE = 365
COLUNAS_ESPERADAS = ['cliente', 'valor', 'data']

# ============================================
# INICIALIZACAO DO ESTADO
# ============================================
def inicializar_estado():
    if 'dados_vendas' not in st.session_state:
        st.session_state.dados_vendas = None
    if 'historico_pontos' not in st.session_state:
        st.session_state.historico_pontos = []

inicializar_estado()

# ============================================
# FUNCOES AUXILIARES
# ============================================
def calcular_pontos(valor_venda):
    return round(float(valor_venda) * TAXA_BONIFICACAO, 2)

def calcular_validade(data_venda):
    if isinstance(data_venda, str):
        data_venda = pd.to_datetime(data_venda)
    return data_venda + timedelta(days=DIAS_VALIDADE)

def normalizar_cliente(nome):
    if pd.isna(nome):
        return ""
    return " ".join(str(nome).strip().title().split())

def parse_valor(valor):
    if pd.isna(valor):
        raise ValueError("Valor vazio")
    if isinstance(valor, (int, float)):
        return float(valor)
    valor_str = str(valor).replace("R$", "").replace(" ", "").strip()
    if "," in valor_str and "." in valor_str:
        valor_str = valor_str.replace(".", "").replace(",", ".")
    elif "," in valor_str:
        valor_str = valor_str.replace(",", ".")
    return float(valor_str)

def parse_data(data):
    if pd.isna(data) or str(data).strip() == "":
        raise ValueError("Data vazia")
    if isinstance(data, datetime):
        return data
    # Formatos aceitos, incluindo o do arquivo RelVendaPorData.csv
    formatos = [
        '%d/%m/%Y %H:%M:%S',
        '%d/%m/%Y %H:%M',
        '%d/%m/%Y',
        '%Y-%m-%d',
        '%d-%m-%Y',
        '%Y/%m/%d'
    ]
    data_str = str(data).strip()
    for fmt in formatos:
        try:
            return datetime.strptime(data_str, fmt)
        except ValueError:
            continue
    return pd.to_datetime(data_str)

def processar_csv(arquivo):
    try:
        # Leitura adaptada para o formato RelVendaPorData.csv
        # Separador ';', sem cabeçalho, aspas duplas
        df = pd.read_csv(
            arquivo,
            sep=';',
            header=None,
            quotechar='"',
            encoding='utf-8'
        )

        # Verifica se o número de colunas é o esperado (8 colunas)
        if df.shape[1] < 8:
            st.error(
                f"O arquivo deve ter pelo menos 8 colunas. "
                f"Encontradas: {df.shape[1]}. "
                "Formato esperado: cupom;cliente;valor_total;desconto;valor_final;loja;pagamento;data"
            )
            return None

        # Atribui nomes às colunas (baseado no arquivo RelVendaPorData.csv)
        df.columns = [
            'cupom', 'cliente', 'valor_total', 'desconto',
            'valor_final', 'loja', 'pagamento', 'data'
        ] + [f'extra_{i}' for i in range(df.shape[1] - 8)]

        if df.empty:
            st.error("O arquivo CSV esta vazio.")
            return None

        registros_validos = []
        erros = []

        for idx, row in df.iterrows():
            try:
                cliente = normalizar_cliente(row['cliente'])
                if not cliente:
                    raise ValueError("Nome do cliente vazio")

                # Usa o valor final (coluna 4) como valor da venda
                valor = parse_valor(row['valor_final'])
                if valor < 0:
                    raise ValueError("Valor negativo")

                data = parse_data(row['data'])

                registros_validos.append({
                    'cliente': cliente,
                    'valor': valor,
                    'data': data
                })
            except Exception as e:
                erros.append(f"Linha {idx + 1}: {e}")

        if erros:
            with st.expander(f"{len(erros)} linha(s) com erro (ignoradas)"):
                for erro in erros:
                    st.warning(erro)

        if not registros_validos:
            st.error("Nenhuma linha valida encontrada no arquivo.")
            return None

        df_limpo = pd.DataFrame(registros_validos)
        df_limpo['pontos'] = df_limpo['valor'].apply(calcular_pontos)
        df_limpo['validade'] = df_limpo['data'].apply(calcular_validade)
        df_limpo['data'] = df_limpo['data'].dt.strftime('%Y-%m-%d')
        df_limpo['validade'] = df_limpo['validade'].dt.strftime('%Y-%m-%d')
        df_limpo['data_processamento'] = datetime.now().strftime('%Y-%m-%d %H:%M')
        df_limpo = df_limpo.sort_values('data').reset_index(drop=True)

        return df_limpo

    except pd.errors.EmptyDataError:
        st.error("O arquivo esta vazio ou nao e um CSV valido.")
        return None
    except Exception as e:
        st.error(f"Erro ao processar arquivo: {e}")
        return None

def consolidar_pontos_por_cliente(df):
    if df is None or df.empty:
        return pd.DataFrame(), pd.DataFrame()

    consolidado = df.groupby('cliente').agg({
        'valor': 'sum',
        'pontos': 'sum',
        'data': 'max',
        'validade': 'max'
    }).reset_index()

    consolidado.columns = [
        'Cliente', 'Total Gasto (R$)', 'Pontos Disponiveis (R$)',
        'Ultima Compra', 'Validade'
    ]

    consolidado_display = consolidado.copy()
    consolidado_display['Total Gasto (R$)'] = consolidado_display['Total Gasto (R$)'].apply(
        lambda x: "R$ " + f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    )
    consolidado_display['Pontos Disponiveis (R$)'] = consolidado_display['Pontos Disponiveis (R$)'].apply(
        lambda x: "R$ " + f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    )

    return consolidado, consolidado_display

def verificar_pontos_expirados(df):
    if df is None or df.empty:
        return pd.DataFrame()
    hoje = pd.Timestamp.now().normalize()
    df_temp = df.copy()
    df_temp['validade_dt'] = pd.to_datetime(df_temp['validade'])
    expirados = df_temp[df_temp['validade_dt'] < hoje].copy()
    if not expirados.empty:
        expirados['dias_expirado'] = (hoje - expirados['validade_dt']).dt.days
    return expirados

def formatar_moeda(valor):
    return "R$ " + f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# ============================================
# INTERFACE PRINCIPAL
# ============================================
st.title("🎁 Sistema de Bonificacao de Vendas")
st.markdown("---")

with st.sidebar:
    st.header("📋 Menu")
    opcao = st.radio(
        "Selecione uma opcao:",
        ["📤 Upload de Vendas", "📊 Dashboard", "👥 Clientes", "⚠️ Pontos Expirados", "ℹ️ Informacoes"]
    )

    st.markdown("---")
    st.markdown("### 💡 Como funciona")
    st.info(
        "Cliente gasta R$ 1.000,00\n"
        "Recebe R$ 10,00 em pontos (1%)\n"
        "Validade: " + str(DIAS_VALIDADE) + " dias"
    )

    if st.session_state.dados_vendas is not None:
        st.success("✅ " + str(len(st.session_state.dados_vendas)) + " registros carregados")

# ============================================
# PAGINA: UPLOAD
# ============================================
if opcao == "📤 Upload de Vendas":
    st.header("📤 Upload do Arquivo de Vendas")

    st.markdown("**Formato esperado do CSV (RelVendaPorData.csv):**")
    st.code(
        '"00425";"CONSUMIDOR FINAL";"3,50";"0,00";"3,50";"APOLLO32";"A VISTA";"01/08/2026  11:11:13"\n'
        '"00426";"CONSUMIDOR FINAL";"8,00";"0,00";"8,00";"APOLLO32";"A VISTA";"01/08/2026  11:43:38"',
        language="csv"
    )
    st.markdown(
        "**Colunas (sem cabeçalho):** cupom; cliente; valor_total; desconto; "
        "valor_final; loja; pagamento; data_hora"
    )

    # Modelo de exemplo adaptado (opcional)
    exemplo_csv = (
        '"00001";"CLIENTE EXEMPLO";"100,00";"0,00";"100,00";"LOJA";"PIX";"01/01/2025  10:00:00"\n'
        '"00002";"OUTRO CLIENTE";"250,50";"0,00";"250,50";"LOJA";"CARTÃO";"02/01/2025  14:30:00"'
    )

    st.download_button(
        label="📥 Baixar modelo",
        data=exemplo_csv,
        file_name="modelo_vendas.csv",
        mime="text/csv"
    )

    st.markdown("---")

    arquivo = st.file_uploader(
        "Selecione o arquivo CSV de vendas",
        type=['csv'],
        help="O arquivo deve seguir o formato do RelVendaPorData.csv"
    )

    if arquivo is not None:
        df = processar_csv(arquivo)

        if df is not None:
            st.session_state.dados_vendas = df

            st.session_state.historico_pontos.append({
                'data_upload': datetime.now().strftime('%Y-%m-%d %H:%M'),
                'arquivo': arquivo.name,
                'registros': len(df),
                'total_vendas': df['valor'].sum(),
                'total_pontos': df['pontos'].sum()
            })

            st.success(f"✅ Arquivo processado com sucesso! {len(df)} registros validos.")

            st.subheader("📋 Preview dos Dados Processados")
            st.dataframe(df, use_container_width=True, hide_index=True)

            st.markdown("### 📊 Resumo")
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total de Vendas", formatar_moeda(df['valor'].sum()))
            with col2:
                st.metric("Total de Pontos", formatar_moeda(df['pontos'].sum()))
            with col3:
                st.metric("Clientes Unicos", df['cliente'].nunique())
            with col4:
                st.metric("Ticket Medio", formatar_moeda(df['valor'].mean()))

# ============================================
# PAGINA: DASHBOARD
# ============================================
elif opcao == "📊 Dashboard":
    st.header("📊 Dashboard de Vendas e Pontos")

    if st.session_state.dados_vendas is None:
        st.warning("Nenhum dado carregado. Faca o upload do arquivo CSV primeiro.")
    else:
        df = st.session_state.dados_vendas

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("💰 Total de Vendas", formatar_moeda(df['valor'].sum()))
        with col2:
            st.metric("🎁 Total de Pontos", formatar_moeda(df['pontos'].sum()))
        with col3:
            st.metric("👥 Total de Clientes", df['cliente'].nunique())
        with col4:
            st.metric("📈 Ticket Medio", formatar_moeda(df['valor'].mean()))

        st.markdown("---")

        col1, col2 = st.columns(2)

        with col1:
            st.subheader("🏆 Top 10 Clientes por Valor")
            top_clientes = df.groupby('cliente')['valor'].sum().nlargest(10).reset_index()
            top_clientes.columns = ['Cliente', 'Valor']
            st.bar_chart(top_clientes.set_index('Cliente'))

        with col2:
            st.subheader("🎁 Top 10 Clientes por Pontos")
            top_pontos = df.groupby('cliente')['pontos'].sum().nlargest(10).reset_index()
            top_pontos.columns = ['Cliente', 'Pontos']
            st.bar_chart(top_pontos.set_index('Cliente'))

        st.markdown("---")

        if df['data'].nunique() > 1:
            st.subheader("📅 Evolucao de Vendas por Data")
            vendas_data = df.groupby('data')['valor'].sum().reset_index()
            vendas_data.columns = ['Data', 'Valor']
            st.line_chart(vendas_data.set_index('Data'))

        if st.session_state.historico_pontos:
            st.markdown("---")
            st.subheader("📅 Historico de Uploads")
            historico_df = pd.DataFrame(st.session_state.historico_pontos)
            historico_df['total_vendas'] = historico_df['total_vendas'].apply(formatar_moeda)
            historico_df['total_pontos'] = historico_df['total_pontos'].apply(formatar_moeda)
            historico_df.columns = ['Data Upload', 'Arquivo', 'Registros', 'Total Vendas', 'Total Pontos']
            st.dataframe(historico_df, use_container_width=True, hide_index=True)

# ============================================
# PAGINA: CLIENTES
# ============================================
elif opcao == "👥 Clientes":
    st.header("👥 Lista de Clientes e Pontos")

    if st.session_state.dados_vendas is None:
        st.warning("Nenhum dado carregado. Faca o upload do arquivo CSV primeiro.")
    else:
        df = st.session_state.dados_vendas
        consolidado, consolidado_display = consolidar_pontos_por_cliente(df)

        busca = st.text_input("🔍 Buscar cliente:", "")

        if busca:
            mask = consolidado_display['Cliente'].str.contains(busca, case=False, na=False)
            consolidado_display_filtrado = consolidado_display[mask]
        else:
            consolidado_display_filtrado = consolidado_display

        st.dataframe(consolidado_display_filtrado, use_container_width=True, hide_index=True)

        st.markdown("---")
        st.subheader("📊 Resumo")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.info(f"**Clientes listados:** {len(consolidado_display_filtrado)}")
        with col2:
            total_pontos = consolidado['Pontos Disponiveis (R$)'].sum()
            st.info(f"**Total de pontos:** {formatar_moeda(total_pontos)}")
        with col3:
            total_gasto = consolidado['Total Gasto (R$)'].sum()
            st.info(f"**Total gasto:** {formatar_moeda(total_gasto)}")

        csv_export = consolidado.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="📥 Exportar lista de clientes (CSV)",
            data=csv_export,
            file_name=f"clientes_pontos_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )

# ============================================
# PAGINA: PONTOS EXPIRADOS
# ============================================
elif opcao == "⚠️ Pontos Expirados":
    st.header("⚠️ Pontos Expirados")

    if st.session_state.dados_vendas is None:
        st.warning("Nenhum dado carregado. Faca o upload do arquivo CSV primeiro.")
    else:
        df = st.session_state.dados_vendas
        expirados = verificar_pontos_expirados(df)

        if expirados.empty:
            st.success("✅ Nenhum ponto expirado ate o momento!")
        else:
            st.error(f"⚠️ {len(expirados)} registro(s) com pontos expirados")

            expirados_display = expirados[['cliente', 'valor', 'pontos', 'data', 'validade', 'dias_expirado']].copy()
            expirados_display.columns = ['Cliente', 'Valor', 'Pontos', 'Data Venda', 'Validade', 'Dias Expirado']
            expirados_display['Valor'] = expirados_display['Valor'].apply(formatar_moeda)
            expirados_display['Pontos'] = expirados_display['Pontos'].apply(formatar_moeda)

            st.dataframe(expirados_display, use_container_width=True, hide_index=True)

            st.markdown("---")
            total_expirado = expirados['pontos'].sum()
            st.metric("💸 Total de Pontos Expirados", formatar_moeda(total_expirado))

# ============================================
# PAGINA: INFORMACOES
# ============================================
elif opcao == "ℹ️ Informacoes":
    st.header("ℹ️ Informacoes do Sistema")

    st.markdown("## 🎁 Sistema de Bonificacao de Vendas")

    st.markdown("### Regras de Bonificacao")
    st.markdown(
        "- **Taxa de retorno:** 1% do valor gasto\n"
        "- **Validade dos pontos:** " + str(DIAS_VALIDADE) + " dias (1 ano)\n"
        "- **Conversao:** Pontos podem ser convertidos em mercadoria"
    )

    st.markdown("### Exemplo de Calculo")
    st.markdown(
        "| Valor Gasto | Pontos Gerados |\n"
        "|-------------|----------------|\n"
        "| R$ 100,00   | R$ 1,00        |\n"
        "| R$ 500,00   | R$ 5,00        |\n"
        "| R$ 1.000,00 | R$ 10,00       |\n"
        "| R$ 5.000,00 | R$ 50,00       |"
    )

    st.markdown("### Formato do Arquivo CSV")
    st.markdown(
        "O arquivo deve seguir o formato **RelVendaPorData.csv**:\n"
        "- Separador: ponto e vírgula (`;`)\n"
        "- Sem linha de cabeçalho\n"
        "- Campos entre aspas duplas (`\"`)\n"
        "- Colunas: cupom; cliente; valor_total; desconto; valor_final; loja; pagamento; data_hora\n"
        "- Valores com vírgula decimal (ex: `3,50`)\n"
        "- Datas no formato `dd/mm/aaaa HH:MM:SS`"
    )

    st.markdown("### Fluxo de Uso")
    st.markdown(
        "1. Faca upload do arquivo CSV mensal\n"
        "2. O sistema calcula automaticamente os pontos (1%)\n"
        "3. Consulte o dashboard para visualizar metricas\n"
        "4. Acompanhe a validade dos pontos na aba de clientes\n"
        "5. Exporte relatorios quando necessario"
    )

# ============================================
# RODAPE
# ============================================
st.markdown("---")
st.markdown(
    "<div style='text-align: center; color: gray;'>"
    "Sistema de Bonificacao v1.2 | Desenvolvido com Streamlit"
    "</div>",
    unsafe_allow_html=True
)