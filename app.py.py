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

# ============================================
# INICIALIZAÇÃO DO ESTADO
# ============================================
def inicializar_estado():
    """Inicializa o estado da sessão se não existir"""
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
    return round(valor_venda * TAXA_BONIFICACAO, 2)

def calcular_validade(data_venda):
    """Calcula data de validade dos pontos (1 ano)"""
    if isinstance(data_venda, str):
        data_venda = datetime.strptime(data_venda, '%Y-%m-%d')
    return data_venda + timedelta(days=DIAS_VALIDADE)

def processar_csv(arquivo):
    """Processa o arquivo CSV de vendas"""
    try:
        df = pd.read_csv(arquivo)
        
        # Verificar colunas necessárias
        colunas_necessarias = ['cliente', 'valor']
        colunas_encontradas = [col.lower() for col in df.columns]
        
        # Mapear colunas (aceita variações)
        mapeamento = {}
        for col in df.columns:
            col_lower = col.lower()
            if 'cliente' in col_lower or 'nome' in col_lower:
                mapeamento[col] = 'cliente'
            elif 'valor' in col_lower or 'total' in col_lower or 'venda' in col_lower:
                mapeamento[col] = 'valor'
            elif 'data' in col_lower:
                mapeamento[col] = 'data'
        
        df = df.rename(columns=mapeamento)
        
        # Verificar se temos as colunas essenciais
        if 'cliente' not in df.columns or 'valor' not in df.columns:
            st.error("❌ O arquivo precisa ter colunas de 'cliente' e 'valor'")
            return None
        
        # Adicionar data se não existir
        if 'data' not in df.columns:
            df['data'] = datetime.now().strftime('%Y-%m-%d')
        
        # Calcular pontos
        df['pontos'] = df['valor'].apply(calcular_pontos)
        df['validade'] = df['data'].apply(calcular_validade)
        df['data_processamento'] = datetime.now().strftime('%Y-%m-%d %H:%M')
        
        return df
    
    except Exception as e:
        st.error(f"❌ Erro ao processar arquivo: {str(e)}")
        return None

def consolidar_pontos_por_cliente(df):
    """Agrupa pontos por cliente"""
    if df is None or df.empty:
        return pd.DataFrame()
    
    consolidado = df.groupby('cliente').agg({
        'valor': 'sum',
        'pontos': 'sum',
        'data': 'max',  # Última compra
        'validade': 'max'  # Validade mais distante
    }).reset_index()
    
    consolidado.columns = ['Cliente', 'Total Gasto (R$)', 'Pontos Disponíveis', 'Última Compra', 'Validade']
    consolidado['Total Gasto (R$)'] = consolidado['Total Gasto (R$)'].apply(lambda x: f"R$ {x:,.2f}")
    consolidado['Pontos Disponíveis'] = consolidado['Pontos Disponíveis'].apply(lambda x: f"R$ {x:,.2f}")
    
    return consolidado.sort_values('Cliente')

def verificar_pontos_expirados(df):
    """Verifica pontos expirados"""
    if df is None or df.empty:
        return pd.DataFrame()
    
    hoje = datetime.now()
    df['validade_dt'] = pd.to_datetime(df['validade'])
    expirados = df[df['validade_dt'] < hoje].copy()
    
    if not expirados.empty:
        expirados['dias_expirado'] = (hoje - expirados['validade_dt']).dt.days
    
    return expirados

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

# ============================================
# PÁGINA: UPLOAD DE VENDAS
# ============================================
if opcao == "📤 Upload de Vendas":
    st.header("📤 Upload do Arquivo de Vendas")
    
    st.markdown("""
    **Formato esperado do CSV:**
    - Coluna `cliente` ou `nome`: Nome do cliente
    - Coluna `valor` ou `total`: Valor da venda
    - Coluna `data` (opcional): Data da venda (YYYY-MM-DD)
    """)
    
    # Exemplo de CSV para download
    exemplo_csv = """cliente,valor,data
João Silva,1500.00,2025-01-15
Maria Santos,2300.50,2025-01-20
Pedro Oliveira,850.00,2025-01-25
Ana Costa,3200.00,2025-02-01"""
    
    st.download_button(
        label="📥 Baixar modelo de CSV",
        data=exemplo_csv,
        file_name="modelo_vendas.csv",
        mime="text/csv"
    )
    
    st.markdown("---")
    
    arquivo = st.file_uploader(
        "Selecione o arquivo CSV de vendas",
        type=['csv'],
        help="Arquivo gerado pelo seu sistema de vendas"
    )
    
    if arquivo is not None:
        df = processar_csv(arquivo)
        
        if df is not None:
            st.session_state.dados_vendas = df
            
            # Adicionar ao histórico
            st.session_state.historico_pontos.append({
                'data_upload': datetime.now().strftime('%Y-%m-%d %H:%M'),
                'registros': len(df),
                'total_vendas': df['valor'].sum(),
                'total_pontos': df['pontos'].sum()
            })
            
            st.success(f"✅ Arquivo processado com sucesso! {len(df)} registros encontrados.")
            
            # Preview dos dados
            st.subheader("📋 Preview dos Dados Processados")
            st.dataframe(df, use_container_width=True)
            
            # Métricas
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total de Vendas", f"R$ {df['valor'].sum():,.2f}")
            with col2:
                st.metric("Total de Pontos Gerados", f"R$ {df['pontos'].sum():,.2f}")
            with col3:
                st.metric("Clientes Únicos", df['cliente'].nunique())

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
            st.metric(
                "💰 Total de Vendas",
                f"R$ {df['valor'].sum():,.2f}"
            )
        
        with col2:
            st.metric(
                "🎁 Total de Pontos",
                f"R$ {df['pontos'].sum():,.2f}"
            )
        
        with col3:
            st.metric(
                "👥 Total de Clientes",
                df['cliente'].nunique()
            )
        
        with col4:
            ticket_medio = df['valor'].mean()
            st.metric(
                "📈 Ticket Médio",
                f"R$ {ticket_medio:,.2f}"
            )
        
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
        
        # Histórico de uploads
        if st.session_state.historico_pontos:
            st.subheader("📅 Histórico de Uploads")
            historico_df = pd.DataFrame(st.session_state.historico_pontos)
            historico_df.columns = ['Data Upload', 'Registros', 'Total Vendas', 'Total Pontos']
            historico_df['Total Vendas'] = historico_df['Total Vendas'].apply(lambda x: f"R$ {x:,.2f}")
            historico_df['Total Pontos'] = historico_df['Total Pontos'].apply(lambda x: f"R$ {x:,.2f}")
            st.dataframe(historico_df, use_container_width=True)

# ============================================
# PÁGINA: CLIENTES
# ============================================
elif opcao == "👥 Clientes":
    st.header("👥 Lista de Clientes e Pontos")
    
    if st.session_state.dados_vendas is None:
        st.warning("⚠️ Nenhum dado carregado. Faça o upload do arquivo CSV primeiro.")
    else:
        df = st.session_state.dados_vendas
        consolidado = consolidar_pontos_por_cliente(df)
        
        # Filtro de busca
        busca = st.text_input("🔍 Buscar cliente:", "")
        
        if busca:
            consolidado = consolidado[
                consolidado['Cliente'].str.contains(busca, case=False, na=False)
            ]
        
        st.dataframe(consolidado, use_container_width=True, hide_index=True)
        
        # Resumo
        st.markdown("---")
        st.subheader("📊 Resumo")
        
        col1, col2 = st.columns(2)
        with col1:
            st.info(f"**Total de clientes:** {len(consolidado)}")
        with col2:
            total_pontos = df['pontos'].sum()
            st.info(f"**Total de pontos distribuídos:** R$ {total_pontos:,.2f}")

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
            
            # Mostrar tabela de expirados
            expirados_display = expirados[['cliente', 'valor', 'pontos', 'data', 'validade']].copy()
            expirados_display.columns = ['Cliente', 'Valor', 'Pontos', 'Data Venda', 'Validade']
            expirados_display['Valor'] = expirados_display['Valor'].apply(lambda x: f"R$ {x:,.2f}")
            expirados_display['Pontos'] = expirados_display['Pontos'].apply(lambda x: f"R$ {x:,.2f}")
            
            st.dataframe(expirados_display, use_container_width=True, hide_index=True)
            
            # Resumo de perdas
            st.markdown("---")
            total_expirado = expirados['pontos'].sum()
            st.metric("💸 Total de Pontos Expirados", f"R$ {total_expirado:,.2f}")

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
    O arquivo deve conter as seguintes colunas:
    - `cliente` ou `nome`: Nome do cliente
    - `valor` ou `total`: Valor da compra
    - `data` (opcional): Data da venda no formato YYYY-MM-DD
    
    ### Fluxo de Uso
    1. Faça upload do arquivo CSV mensal
    2. O sistema calcula automaticamente os pontos
    3. Consulte o dashboard para visualizar métricas
    4. Acompanhe a validade dos pontos na aba de clientes
    """)

# ============================================
# RODAPÉ
# ============================================
st.markdown("---")
st.markdown(
    "<div style='text-align: center; color: gray;'>"
    "Sistema de Bonificação v1.0 | Desenvolvido com Streamlit"
    "</div>",
    unsafe_allow_html=True
)