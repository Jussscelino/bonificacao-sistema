import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import io

# ============================================
# CONFIGURAÇÃO DA PÁGINA
# ============================================
st.set_page_config(
    page_title="Sistema de Bonificação",
    page_icon="🎁",
    layout="wide"
)

# ============================================
# CONSTANTES
# ============================================
TAXA_BONIFICACAO = 0.01  # 1% de retorno
DIAS_VALIDADE = 365      # 1 ano de validade
COLUNAS_ESPERADAS = ['cliente', 'valor', 'data']

# ============================================
# INICIALIZAÇÃO DO ESTADO
# ============================================
def inicializar_estado():
    if 'dados_vendas' not in st.session_state:
        st.session_state.dados_vendas = None
    if 'historico_pontos' not in st.session_state:
        st.session_state.historico_pontos = []

inicializar_estado()

# ============================================
# FUNÇÕES AUXILIARES
# ============================================
def calcular_pontos(valor_venda):
    """Calcula pontos baseado no valor da venda (1%)"""
    return round(float(valor_venda) * TAXA_BONIFICACAO, 2)

def calcular_validade(data_venda):
    """Calcula data de validade dos pontos (1 ano após a venda)"""
    if isinstance(data_venda, str):
        data_venda = pd.to_datetime(data_venda)
    return data_venda + timedelta(days=DIAS_VALIDADE)

def normalizar_cliente(nome):
    """Normaliza nome do cliente para evitar duplicatas"""
    if pd.isna(nome):
        return ""
    # Remove espaços extras e padroniza capitalização
    return " ".join(str(nome).strip().title().split())

def parse_valor(valor):
    """
    Converte valor para float, aceitando:
    - Ponto decimal: 1500.00
    - Vírgula decimal: 1500,00
    - Com símbolo R$: R$ 1.500,00
    """
    if pd.isna(valor):
        raise ValueError("Valor vazio")
    
    if isinstance(valor, (int, float)):
        return float(valor)
    
    # Remove R$, espaços
    valor_str = str(valor).replace("R$", "").replace(" ", "").strip()
    
    # Se tem vírgula E ponto: assume ponto como milhar (padrão BR)
    if "," in valor_str and "." in valor_str:
        valor_str = valor_str.replace(".", "").replace(",", ".")
    # Se tem apenas vírgula: assume vírgula como decimal
    elif "," in valor_str:
        valor_str = valor_str.replace(",", ".")
    
    return float(valor_str)

def parse_data(data):
    """Tenta converter data em vários formatos comuns"""
    if pd.isna(data) or str(data).strip() == "":
        raise ValueError("Data vazia")
    
    if isinstance(data, datetime):
        return data
    
    formatos = ['%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%Y/%m/%d']
    data_str = str(data).strip()
    
    for fmt in formatos:
        try:
            return datetime.strptime(data_str, fmt)
        except ValueError:
            continue
    
    # Última tentativa: deixa o pandas tentar
    return pd.to_datetime(data_str)

def processar_csv(arquivo):
    """
    Processa o arquivo CSV de vendas com validação completa.
    Formato esperado: cliente, valor, data
    """
    try:
        # Ler CSV
        df = pd.read_csv(arquivo)
        
        # Normalizar nomes de colunas (minúsculas, sem espaços)
        df.columns = [str(c).strip().lower() for c in df.columns]
        
        # Validar colunas obrigatórias
        colunas_faltantes = [c for c in COLUNAS_ESPERADAS if c not in df.columns]
        if colunas_faltantes:
            st.error(
                f"❌ Colunas obrigatórias faltando: **{', '.join(colunas_faltantes)}**\n\n"
                f"Colunas encontradas: {', '.join(df.columns.tolist())}\n\n"
                f"Formato esperado: **cliente, valor, data**"
            )
            return None
        
        # Validar se há dados
        if df.empty:
            st.error("❌ O arquivo CSV está vazio.")
            return None
        
        # Processar linha por linha com tratamento de erros
        registros_validos = []
        erros = []
        
        for idx, row in df.iterrows():
            try:
                cliente = normalizar_cliente(row['cliente'])
                if not cliente:
                    raise ValueError("Nome do cliente vazio")
                
                valor = parse_valor(row['valor'])
                if valor < 0:
                    raise ValueError("Valor negativo")
                
                data = parse_data(row['data'])
                
                registros_validos.append({
                    'cliente': cliente,
                    'valor': valor,
                    'data': data
                })
            except Exception as e:
                erros.append(f"Linha {idx + 2}: {str(e)}")
        
        # Reportar erros
        if erros:
            with st.expander(f"⚠️ {len(erros)} linha(s) com erro (ignoradas)"):
                for erro in erros:
                    st.warning(erro)
        
        if not registros_validos:
            st.error("❌ Nenhuma linha válida encontrada no arquivo.")
            return None
        
        # Criar DataFrame limpo
        df_limpo = pd.DataFrame(registros_validos)
        
        # Calcular pontos e validade
        df_limpo['pontos'] = df_limpo['valor'].apply(calcular_pontos)
        df_limpo['validade'] = df_limpo['data'].apply(calcular_validade)
        df_limpo['data'] = df_limpo['data'].dt.strftime('%Y-%m-%d')
        df_limpo['validade'] = df_limpo['validade'].dt.strftime('%Y-%m-%d')
        df_limpo['data_processamento'] = datetime.now().strftime('%Y-%m-%d %H:%M')
        
        # Ordenar por data
        df_limpo = df_limpo.sort_values('data').reset_index(drop=True)
        
        return df_limpo
    
    except pd.errors.EmptyDataError:
        st.error("❌ O arquivo está vazio ou não é um CSV válido.")
        return None
    except Exception as e:
        st.error(f"❌ Erro ao processar arquivo: {str(e)}")
        return None

def consolidar_pontos_por_cliente(df):
    """Agrupa pontos por cliente (somando múltiplas compras)"""
    if df is None or df.empty:
        return pd.DataFrame()
    
    consolidado = df.groupby('cliente').agg({
        'valor': 'sum',
        'pontos': 'sum',
        'data': 'max',
        'validade': 'max'
    }).reset_index()
    
    consolidado.columns = [
        'Cliente', 'Total Gasto (R$)', 'Pontos Disponíveis (R$)',
        'Última Compra', 'Validade'
    ]
    
    # Formatar para exibição
    consolidado_display = consolidado.copy()
    consolidado_display['Total Gasto (R$)'] = consolidado_display['Total Gasto (R$)'].apply(
        lambda x: f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    )
    consolidado_display['Pontos Disponíveis (R$)'] = consolidado_display['Pontos Disponíveis (R$)'].apply(
        lambda x: f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    )
    
    return consolidado, consolidado_display

def verificar_pontos_expirados(df):
    """Verifica pontos expirados"""
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
    """Formata número como moeda brasileira"""
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# ============================================
# INTERFACE PRINCIPAL
# ============================================
st.title("🎁 Sistema de Bonificação de Vendas")
st.markdown("---")

# Sidebar
with st.sidebar:
    st.header("📋 Menu")
    opcao = st.radio(
        "Selecione uma opção:",
        ["📤 Upload de Vendas", "📊 Dashboard", "👥 Clientes", "⚠️ Pontos Expirados", "ℹ️ Informações"]
    )
    
    st.markdown("---")
    st.markdown("### 💡 Como funciona")
    st.info(
        f"• Cliente gasta R$ 1.000,00\n"
        f"• Recebe R$ 10,00 em pontos (1%)\n"
        f"• Validade: {DIAS_VALIDADE} dias"
    )
    
    # Indicador de dados carregados
    if st.session_state.dados_vendas is not None:
        st.success(f"✅ {len(st.session_state.dados_vendas)} registros carregados")

# ============================================
# PÁGINA: UPLOAD DE VENDAS
# ============================================
if opcao == "📤 Upload de Vendas":
    st.header("📤 Upload do Arquivo de Vendas")
    
    st.markdown("""
    **Formato esperado do CSV:**
    
    | cliente | valor | data |
    |---------|-------|------|
    | João Silva | 1500.00 | 2025-01-15 |
    | Maria Santos | 2300.50 | 2025-01-20 |
    """)
    
    # Exemplo de CSV para download
    exemplo_csv = """cliente,valor,data
João Silva,1500.00,2025-01-15
Maria Santos,2300.50,2025-01-20
Pedro Oliveira,850.00,2025-01-25
Ana Costa,3200.00,2025-02-01"""
    
    col1, col2 = st.columns([1, 3])
    with col1:
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
        help="O arquivo deve conter as colunas: cliente, valor, data"
    )
    
    if arquivo is not None:
        df = processar_csv(arquivo)
        
        if df is not None:
            st.session_state.dados_vendas = df
            
            # Adicionar ao histórico
            st.session_state.historico_pontos.append({
                'data_upload': datetime.now().strftime('%Y-%m-%d %H:%M'),
                'arquivo': arquivo.name,
                'registros': len(df),
                'total_vendas': df['valor'].sum(),
                'total_pontos': df['pontos'].sum()
            })
            
            st.success(f"✅ Arquivo processado com sucesso! {len(df)} registros válidos.")
            
            # Preview dos dados
            st.subheader("📋 Preview dos Dados Processados")
            st.dataframe(df, use_container_width=True, hide_index=True)
            
            # Métricas
            st.markdown("### 📊 Resumo")
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total de Vendas", formatar_moeda(df['valor'].sum()))
            with col2:
                st.metric("Total de Pontos", formatar_moeda(df['pontos'].sum()))
            with col3:
                st.metric("Clientes Únicos", df['cliente'].nunique())
            with col4:
                st.metric("Ticket Médio", formatar_moeda(df['valor'].mean()))

# ============================================
# PÁGINA: DASHBOARD
# ============================================
elif opcao == "📊 Dashboard":
    st.header("📊 Dashboard de Vendas e Pontos")
    
    if st.session_state.dados_vendas is None:
        st.warning("⚠️ Nenhum dado carregado. Faça o upload do arquivo CSV primeiro.")
    else:
        df = st.session_state.dados_vendas
        
        # Métricas principais
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("💰 Total de Vendas", formatar_moeda(df['valor'].sum()))
        with col2:
            st.metric("🎁 Total de Pontos", formatar_moeda(df['pontos'].sum()))
        with col3:
            st.metric("👥 Total de Clientes", df['cliente'].nunique())
        with col4:
            st.metric("📈 Ticket Médio", formatar_moeda(df['valor'].mean()))
        
        st.markdown("---")
        
        # Gráficos
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
        
        # Vendas por data (se houver múltiplas datas)
        if df['data'].nunique() > 1:
            st.subheader("📅 Evolução de Vendas por Data")
            vendas_data = df.groupby('data')['valor'].sum().reset_index()
            vendas_data.columns = ['Data', 'Valor']
            st.line_chart(vendas_data.set_index('Data'))
        
        # Histórico de uploads
        if st.session_state.historico_pontos:
            st.markdown("---")
            st.subheader("📅 Histórico de Uploads")
            historico_df = pd.DataFrame(st.session_state.historico_pontos)
            historico_df['total_vendas'] = historico_df['total_vendas'].apply(formatar_moeda)
            historico_df['total_pontos'] = historico_df['total_pontos'].apply(formatar_moeda)
            historico_df.columns = ['Data Upload', 'Arquivo', 'Registros', 'Total Vendas', 'Total Pontos']
            st.dataframe(historico_df, use_container_width=True, hide_index=True)

# ============================================
# PÁGINA: CLIENTES
# ============================================
elif opcao == "👥 Clientes":
    st.header("👥 Lista de Clientes e Pontos")
    
    if st.session_state.dados_vendas is None:
        st.warning("⚠️ Nenhum dado carregado. Faça o upload do arquivo CSV primeiro.")
    else:
        df = st.session_state.dados_vendas
        consolidado, consolidado_display = consolidar_pontos_por_cliente(df)
        
        # Filtro de busca
        busca = st.text_input("🔍 Buscar cliente:", "")
        
        if busca:
            mask = consolidado_display['Cliente'].str.contains(busca, case=False, na=False)
            consolidado_display_filtrado = consolidado_display[mask]
        else:
            consolidado_display_filtrado = consolidado_display
        
        st.dataframe(consolidado_display_filtrado, use_container_width=True, hide_index=True)
        
        # Resumo
        st.markdown("---")
        st.subheader("📊 Resumo")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.info(f"**Clientes listados:** {len(consolidado_display_filtrado)}")
        with col2:
            total_pontos = consolidado['Pontos Disponíveis (R$)'].sum()
            st.info(f"**Total de pontos:** {formatar_moeda(total_pontos)}")
        with col3:
            total_gasto = consolidado['Total Gasto (R$)'].sum()
            st.info(f"**Total gasto:** {formatar_moeda(total_gasto)}")
        
        # Botão de download
        csv_export = consolidado.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="📥 Exportar lista de clientes (CSV)",
            data=csv_export,
            file_name=f"clientes_pontos_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )

# ============================================
# PÁGINA: PONTOS EXPIRADOS
# ============================================
elif opcao == "⚠️ Pontos Expirados":
    st.header("⚠️ Pontos Expirados")
    
    if st.session_state.dados_vendas is None:
        st.warning("⚠️ Nenhum dado carregado. Faça o upload do arquivo CSV primeiro.")
    else:
        df = st.session_state.dados_vendas
        expirados = verificar_pontos_expirados(df)
        
        if expirados.empty:
            st.success("✅ Nenhum ponto expirado até o momento!")
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
# PÁGINA: INFORMAÇÕES
# ============================================
elif opcao == "ℹ️ Informações":
    st.header("ℹ️ Informações do Sistema")
    
    st.markdown(f"""
    ## 🎁 Sistema de Bonificação de Vendas
    
    ### Regras de Bonificação
    - **Taxa de retorno:** 1% do valor gasto
    - **Validade dos pontos:** {DIAS_VALIDADE} dias (1 ano)
    - **Conversão:** Pontos podem ser convertidos em mercadoria
    
    ### Exemplo de Cálculo
    | Valor Gasto | Pontos Gerados |
    |-------------|----------------|
    | R$ 100,00   | R$ 1,00        |
    | R$ 500,00   | R$ 5,00        |
    | R$ 1.000,00 | R$ 10,00       |
    | R$ 5.000,00 | R$ 50,00       |
    
    ### Formato do Arquivo CSV
    O arquivo deve conter exatamente estas colunas:
    