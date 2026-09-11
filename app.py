import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import hashlib

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

# ============================================
# INICIALIZACAO DO ESTADO
# ============================================
def inicializar_estado():
    if 'dados_vendas' not in st.session_state:
        # DataFrame acumulado com todas as vendas de todos os uploads
        st.session_state.dados_vendas = pd.DataFrame()
    if 'historico_pontos' not in st.session_state:
        st.session_state.historico_pontos = []
    if 'arquivos_processados' not in st.session_state:
        # Armazena hashes de arquivos já processados para evitar duplicatas
        st.session_state.arquivos_processados = set()

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

def hash_arquivo(arquivo):
    """Gera um hash do conteúdo do arquivo para detectar uploads duplicados."""
    conteudo = arquivo.getvalue()
    return hashlib.md5(conteudo).hexdigest()

def processar_csv(arquivo):
    """Processa o CSV no formato RelVendaPorData.csv e retorna um DataFrame limpo."""
    try:
        df = pd.read_csv(
            arquivo,
            sep=';',
            header=None,
            quotechar='"',
            encoding='utf-8'
        )

        if df.shape[1] < 8:
            st.error(
                f"O arquivo deve ter pelo menos 8 colunas. "
                f"Encontradas: {df.shape[1]}. "
                "Formato esperado: cupom;cliente;valor_total;desconto;valor_final;loja;pagamento;data"
            )
            return None

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
                cupom = str(row['cupom']).strip() if not pd.isna(row['cupom']) else ""
                cliente = normalizar_cliente(row['cliente'])
                if not cliente:
                    raise ValueError("Nome do cliente vazio")

                valor = parse_valor(row['valor_final'])
                if valor < 0:
                    raise ValueError("Valor negativo")

                data = parse_data(row['data'])
                loja = str(row['loja']).strip() if not pd.isna(row['loja']) else ""
                pagamento = str(row['pagamento']).strip() if not pd.isna(row['pagamento']) else ""

                registros_validos.append({
                    'cupom': cupom,
                    'cliente': cliente,
                    'valor': valor,
                    'data': data,
                    'loja': loja,
                    'pagamento': pagamento
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

        # Mantém datetime internamente; formata apenas para exibição
        df_limpo = df_limpo.sort_values('data').reset_index(drop=True)

        return df_limpo

    except pd.errors.EmptyDataError:
        st.error("O arquivo esta vazio ou nao e um CSV valido.")
        return None
    except Exception as e:
        st.error(f"Erro ao processar arquivo: {e}")
        return None

def acumular_vendas(df_novo):
    """
    Acumula o novo DataFrame ao histórico existente.
    Evita duplicatas pelo número do cupom.
    Retorna (df_acumulado, qtd_novos, qtd_duplicados).
    """
    if st.session_state.dados_vendas.empty:
        st.session_state.dados_vendas = df_novo.copy()
        return st.session_state.dados_vendas, len(df_novo), 0

    df_existente = st.session_state.dados_vendas
    cupons_existentes = set(df_existente['cupom'].astype(str))

    # Filtra apenas registros com cupom novo
    if 'cupom' in df_novo.columns and cupons_existentes:
        mask_novos = ~df_novo['cupom'].astype(str).isin(cupons_existentes)
        df_novos = df_novo[mask_novos].copy()
        qtd_duplicados = len(df_novo) - len(df_novos)
    else:
        df_novos = df_novo.copy()
        qtd_duplicados = 0

    if not df_novos.empty:
        st.session_state.dados_vendas = pd.concat(
            [df_existente, df_novos], ignore_index=True
        ).sort_values('data').reset_index(drop=True)

    return st.session_state.dados_vendas, len(df_novos), qtd_duplicados

def adicionar_colunas_temporais(df):
    """Adiciona colunas calculadas de validade/expiracao baseadas em hoje."""
    if df is None or df.empty:
        return df
    df = df.copy()
    hoje = pd.Timestamp.now().normalize()
    df['data_dt'] = pd.to_datetime(df['data'])
    df['validade_dt'] = pd.to_datetime(df['validade'])
    df['expirado'] = df['validade_dt'] < hoje
    df['dias_para_expirar'] = (df['validade_dt'] - hoje).dt.days
    return df

def consolidar_pontos_por_cliente(df):
    """
    Consolida pontos por cliente considerando apenas pontos NÃO expirados
    como disponíveis. Pontos expirados são contabilizados separadamente.
    """
    if df is None or df.empty:
        return pd.DataFrame(), pd.DataFrame()

    df_calc = adicionar_colunas_temporais(df)

    # Agregação
    consolidado = df_calc.groupby('cliente').agg(
        total_gasto=('valor', 'sum'),
        total_pontos_gerados=('pontos', 'sum'),
        ultima_compra=('data_dt', 'max'),
        qtd_compras=('valor', 'count')
    ).reset_index()

    # Pontos disponíveis (não expirados)
    pontos_disponiveis = df_calc[~df_calc['expirado']].groupby('cliente')['pontos'].sum()
    pontos_expirados = df_calc[df_calc['expirado']].groupby('cliente')['pontos'].sum()

    consolidado['pontos_disponiveis'] = consolidado['cliente'].map(pontos_disponiveis).fillna(0.0)
    consolidado['pontos_expirados'] = consolidado['cliente'].map(pontos_expirados).fillna(0.0)

    # Próxima validade (menor data de validade futura)
    proximas = df_calc[~df_calc['expirado']].groupby('cliente')['validade_dt'].min()
    consolidado['proxima_validade'] = consolidado['cliente'].map(proximas)

    consolidado = consolidado[[
        'cliente', 'total_gasto', 'total_pontos_gerados',
        'pontos_disponiveis', 'pontos_expirados',
        'qtd_compras', 'ultima_compra', 'proxima_validade'
    ]]

    consolidado.columns = [
        'Cliente', 'Total Gasto (R$)', 'Total Pontos Gerados (R$)',
        'Pontos Disponiveis (R$)', 'Pontos Expirados (R$)',
        'Qtd Compras', 'Ultima Compra', 'Proxima Validade'
    ]

    # Formatação para exibição
    consolidado_display = consolidado.copy()
    for col in ['Total Gasto (R$)', 'Total Pontos Gerados (R$)',
                'Pontos Disponiveis (R$)', 'Pontos Expirados (R$)']:
        consolidado_display[col] = consolidado_display[col].apply(formatar_moeda)

    consolidado_display['Ultima Compra'] = pd.to_datetime(
        consolidado_display['Ultima Compra']
    ).dt.strftime('%d/%m/%Y')
    consolidado_display['Proxima Validade'] = pd.to_datetime(
        consolidado_display['Proxima Validade']
    ).dt.strftime('%d/%m/%Y')

    return consolidado, consolidado_display

def verificar_pontos_expirados(df):
    if df is None or df.empty:
        return pd.DataFrame()
    df_calc = adicionar_colunas_temporais(df)
    expirados = df_calc[df_calc['expirado']].copy()
    return expirados

def pontos_a_expirar_em_dias(df, dias=30):
    """Retorna vendas cujos pontos expiram nos próximos N dias."""
    if df is None or df.empty:
        return pd.DataFrame()
    df_calc = adicionar_colunas_temporais(df)
    mask = (df_calc['dias_para_expirar'] >= 0) & (df_calc['dias_para_expirar'] <= dias)
    return df_calc[mask].copy()

def formatar_moeda(valor):
    try:
        return "R$ " + f"{float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (ValueError, TypeError):
        return "R$ 0,00"

# ============================================
# INTERFACE PRINCIPAL
# ============================================
st.title("🎁 Sistema de Bonificacao de Vendas")
st.markdown("---")

with st.sidebar:
    st.header("📋 Menu")
    opcao = st.radio(
        "Selecione uma opcao:",
        [
            "📤 Upload de Vendas",
            "📊 Dashboard",
            "👥 Clientes",
            "📅 A Expirar (30 dias)",
            "⚠️ Pontos Expirados",
            "ℹ️ Informacoes"
        ]
    )

    st.markdown("---")
    st.markdown("### 💡 Como funciona")
    st.info(
        "Cliente gasta R$ 1.000,00\n"
        "Recebe R$ 10,00 em pontos (1%)\n"
        "Validade: " + str(DIAS_VALIDADE) + " dias"
    )

    if not st.session_state.dados_vendas.empty:
        st.success(
            f"✅ {len(st.session_state.dados_vendas)} vendas acumuladas\n"
            f"📁 {len(st.session_state.historico_pontos)} upload(s) realizados"
        )
        if st.button("🗑️ Limpar todos os dados"):
            st.session_state.dados_vendas = pd.DataFrame()
            st.session_state.historico_pontos = []
            st.session_state.arquivos_processados = set()
            st.rerun()

# ============================================
# PAGINA: UPLOAD
# ============================================
if opcao == "📤 Upload de Vendas":
    st.header("📤 Upload do Arquivo de Vendas")
    st.info(
        "💡 **Acumulacao automatica:** Cada novo upload sera somado ao historico. "
        "Vendas duplicadas (mesmo numero de cupom) sao ignoradas automaticamente."
    )

    st.markdown("**Formato esperado (RelVendaPorData.csv):**")
    st.code(
        '"00425";"CONSUMIDOR FINAL";"3,50";"0,00";"3,50";"APOLLO32";"A VISTA";"01/08/2026  11:11:13"\n'
        '"00426";"CONSUMIDOR FINAL";"8,00";"0,00";"8,00";"APOLLO32";"A VISTA";"01/08/2026  11:43:38"',
        language="csv"
    )

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
        file_hash = hash_arquivo(arquivo)

        if file_hash in st.session_state.arquivos_processados:
            st.warning(
                "⚠️ Este arquivo ja foi processado anteriormente. "
                "O upload foi ignorado para evitar duplicatas."
            )
        else:
            df_novo = processar_csv(arquivo)

            if df_novo is not None:
                df_acumulado, qtd_novos, qtd_duplicados = acumular_vendas(df_novo)

                st.session_state.arquivos_processados.add(file_hash)

                st.session_state.historico_pontos.append({
                    'data_upload': datetime.now().strftime('%d/%m/%Y %H:%M'),
                    'arquivo': arquivo.name,
                    'registros_arquivo': len(df_novo),
                    'registros_novos': qtd_novos,
                    'registros_duplicados': qtd_duplicados,
                    'total_vendas_arquivo': df_novo['valor'].sum(),
                    'total_pontos_arquivo': df_novo['pontos'].sum()
                })

                st.success(
                    f"✅ Arquivo processado! "
                    f"**{qtd_novos}** novas vendas adicionadas "
                    f"({qtd_duplicados} duplicadas ignoradas)."
                )

                st.markdown("### 📊 Totais Acumulados no Sistema")
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Total de Vendas", formatar_moeda(df_acumulado['valor'].sum()))
                with col2:
                    st.metric("Total de Pontos", formatar_moeda(df_acumulado['pontos'].sum()))
                with col3:
                    st.metric("Clientes Unicos", df_acumulado['cliente'].nunique())
                with col4:
                    st.metric("Total de Registros", len(df_acumulado))

                st.markdown("### 📋 Preview das Novas Vendas Processadas")
                preview = df_novo.copy()
                preview['data'] = pd.to_datetime(preview['data']).dt.strftime('%d/%m/%Y %H:%M')
                preview['validade'] = pd.to_datetime(preview['validade']).dt.strftime('%d/%m/%Y')
                preview = preview.rename(columns={
                    'cupom': 'Cupom', 'cliente': 'Cliente', 'valor': 'Valor (R$)',
                    'data': 'Data', 'loja': 'Loja', 'pagamento': 'Pagamento',
                    'pontos': 'Pontos (R$)', 'validade': 'Validade'
                })
                st.dataframe(preview, use_container_width=True, hide_index=True)

# ============================================
# PAGINA: DASHBOARD
# ============================================
elif opcao == "📊 Dashboard":
    st.header("📊 Dashboard de Vendas e Pontos")

    if st.session_state.dados_vendas.empty:
        st.warning("Nenhum dado carregado. Faca o upload do arquivo CSV primeiro.")
    else:
        df = st.session_state.dados_vendas
        df_calc = adicionar_colunas_temporais(df)

        total_vendas = df_calc['valor'].sum()
        total_pontos_gerados = df_calc['pontos'].sum()
        pontos_disponiveis = df_calc[~df_calc['expirado']]['pontos'].sum()
        pontos_expirados = df_calc[df_calc['expirado']]['pontos'].sum()

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("💰 Total de Vendas", formatar_moeda(total_vendas))
        with col2:
            st.metric("🎁 Pontos Disponiveis", formatar_moeda(pontos_disponiveis))
        with col3:
            st.metric("👥 Total de Clientes", df_calc['cliente'].nunique())
        with col4:
            st.metric("📈 Ticket Medio", formatar_moeda(df_calc['valor'].mean()))

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("📦 Total de Vendas (qtd)", len(df_calc))
        with col2:
            st.metric("🎯 Total de Pontos Gerados", formatar_moeda(total_pontos_gerados))
        with col3:
            st.metric("💸 Pontos Expirados", formatar_moeda(pontos_expirados))

        st.markdown("---")

        col1, col2 = st.columns(2)

        with col1:
            st.subheader("🏆 Top 10 Clientes por Valor")
            top_clientes = df_calc.groupby('cliente')['valor'].sum().nlargest(10).reset_index()
            top_clientes.columns = ['Cliente', 'Valor']
            st.bar_chart(top_clientes.set_index('Cliente'))

        with col2:
            st.subheader("🎁 Top 10 Clientes por Pontos Disponiveis")
            top_pontos = df_calc[~df_calc['expirado']].groupby('cliente')['pontos'].sum().nlargest(10).reset_index()
            if top_pontos.empty:
                st.info("Nenhum ponto disponivel no momento.")
            else:
                top_pontos.columns = ['Cliente', 'Pontos']
                st.bar_chart(top_pontos.set_index('Cliente'))

        st.markdown("---")

        if df_calc['data'].nunique() > 1:
            st.subheader("📅 Evolucao de Vendas por Data")
            df_calc['data_str'] = df_calc['data_dt'].dt.strftime('%Y-%m-%d')
            vendas_data = df_calc.groupby('data_str')['valor'].sum().reset_index()
            vendas_data.columns = ['Data', 'Valor']
            st.line_chart(vendas_data.set_index('Data'))

        if st.session_state.historico_pontos:
            st.markdown("---")
            st.subheader("📅 Historico de Uploads (acumulativo)")
            historico_df = pd.DataFrame(st.session_state.historico_pontos)
            historico_df = historico_df.rename(columns={
                'data_upload': 'Data Upload',
                'arquivo': 'Arquivo',
                'registros_arquivo': 'Registros',
                'registros_novos': 'Novos',
                'registros_duplicados': 'Duplicados',
                'total_vendas_arquivo': 'Vendas (R$)',
                'total_pontos_arquivo': 'Pontos (R$)'
            })
            historico_df['Vendas (R$)'] = historico_df['Vendas (R$)'].apply(formatar_moeda)
            historico_df['Pontos (R$)'] = historico_df['Pontos (R$)'].apply(formatar_moeda)
            st.dataframe(historico_df, use_container_width=True, hide_index=True)

# ============================================
# PAGINA: CLIENTES
# ============================================
elif opcao == "👥 Clientes":
    st.header("👥 Lista de Clientes e Pontos")

    if st.session_state.dados_vendas.empty:
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
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.info(f"**Clientes listados:** {len(consolidado_display_filtrado)}")
        with col2:
            st.info(f"**Pontos disponiveis:** {formatar_moeda(consolidado['Pontos Disponiveis (R$)'].sum())}")
        with col3:
            st.info(f"**Pontos expirados:** {formatar_moeda(consolidado['Pontos Expirados (R$)'].sum())}")
        with col4:
            st.info(f"**Total gasto:** {formatar_moeda(consolidado['Total Gasto (R$)'].sum())}")

        csv_export = consolidado.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="📥 Exportar lista de clientes (CSV)",
            data=csv_export,
            file_name=f"clientes_pontos_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )

# ============================================
# PAGINA: A EXPIRAR (30 DIAS)
# ============================================
elif opcao == "📅 A Expirar (30 dias)":
    st.header("📅 Pontos a Expirar nos Proximos 30 Dias")

    if st.session_state.dados_vendas.empty:
        st.warning("Nenhum dado carregado. Faca o upload do arquivo CSV primeiro.")
    else:
        df = st.session_state.dados_vendas
        a_expirar = pontos_a_expirar_em_dias(df, dias=30)

        if a_expirar.empty:
            st.success("✅ Nenhum ponto expira nos proximos 30 dias!")
        else:
            st.warning(f"⚠️ {len(a_expirar)} venda(s) com pontos expirando em ate 30 dias")

            display = a_expirar[[
                'cupom', 'cliente', 'valor', 'pontos',
                'data', 'validade', 'dias_para_expirar'
            ]].copy()
            display.columns = [
                'Cupom', 'Cliente', 'Valor', 'Pontos',
                'Data Venda', 'Validade', 'Dias p/ Expirar'
            ]
            display['Valor'] = display['Valor'].apply(formatar_moeda)
            display['Pontos'] = display['Pontos'].apply(formatar_moeda)
            display['Data Venda'] = pd.to_datetime(display['Data Venda']).dt.strftime('%d/%m/%Y')
            display['Validade'] = pd.to_datetime(display['Validade']).dt.strftime('%d/%m/%Y')
            display = display.sort_values('Dias p/ Expirar')

            st.dataframe(display, use_container_width=True, hide_index=True)

            st.markdown("---")
            col1, col2 = st.columns(2)
            with col1:
                st.metric("🎯 Pontos a Expirar (30d)", formatar_moeda(a_expirar['pontos'].sum()))
            with col2:
                st.metric("👥 Clientes Afetados", a_expirar['cliente'].nunique())

# ============================================
# PAGINA: PONTOS EXPIRADOS
# ============================================
elif opcao == "⚠️ Pontos Expirados":
    st.header("⚠️ Pontos Expirados")

    if st.session_state.dados_vendas.empty:
        st.warning("Nenhum dado carregado. Faca o upload do arquivo CSV primeiro.")
    else:
        df = st.session_state.dados_vendas
        expirados = verificar_pontos_expirados(df)

        if expirados.empty:
            st.success("✅ Nenhum ponto expirado ate o momento!")
        else:
            st.error(f"⚠️ {len(expirados)} venda(s) com pontos expirados")

            display = expirados[[
                'cupom', 'cliente', 'valor', 'pontos',
                'data', 'validade', 'dias_para_expirar'
            ]].copy()
            display.columns = [
                'Cupom', 'Cliente', 'Valor', 'Pontos',
                'Data Venda', 'Validade', 'Dias Expirado'
            ]
            display['Valor'] = display['Valor'].apply(formatar_moeda)
            display['Pontos'] = display['Pontos'].apply(formatar_moeda)
            display['Data Venda'] = pd.to_datetime(display['Data Venda']).dt.strftime('%d/%m/%Y')
            display['Validade'] = pd.to_datetime(display['Validade']).dt.strftime('%d/%m/%Y')
            display['Dias Expirado'] = display['Dias Expirado'].abs()
            display = display.sort_values('Dias Expirado', ascending=False)

            st.dataframe(display, use_container_width=True, hide_index=True)

            st.markdown("---")
            col1, col2 = st.columns(2)
            with col1:
                st.metric("💸 Total de Pontos Expirados", formatar_moeda(expirados['pontos'].sum()))
            with col2:
                st.metric("👥 Clientes Afetados", expirados['cliente'].nunique())

# ============================================
# PAGINA: INFORMACOES
# ============================================
elif opcao == "ℹ️ Informacoes":
    st.header("ℹ️ Informacoes do Sistema")

    st.markdown("## 🎁 Sistema de Bonificacao de Vendas")

    st.markdown("### Regras de Bonificacao")
    st.markdown(
        "- **Taxa de retorno:** 1% do valor gasto\n"
        "- **Validade dos pontos:** " + str(DIAS_VALIDADE) + " dias (1 ano) a partir da data da venda\n"
        "- **Controle:** individual por venda (cada cupom tem sua propria validade)\n"
        "- **Conversao:** Pontos podem ser convertidos em mercadoria"
    )

    st.markdown("### Acumulacao de Uploads")
    st.markdown(
        "- Cada novo upload e **somado** ao historico existente\n"
        "- Vendas com **mesmo numero de cupom** sao ignoradas automaticamente\n"
        "- Arquivos identicos (mesmo hash) nao sao reprocessados\n"
        "- Pontos disponiveis sao recalculados a cada consulta com base na data atual"
    )

    st.markdown("### Exemplo de Calculo")
    st.markdown(
        "| Valor Gasto | Pontos Gerados | Validade |\n"
        "|-------------|----------------|----------|\n"
        "| R$ 100,00   | R$ 1,00        | 1 ano apos a venda |\n"
        "| R$ 500,00   | R$ 5,00        | 1 ano apos a venda |\n"
        "| R$ 1.000,00 | R$ 10,00       | 1 ano apos a venda |\n"
        "| R$ 5.000,00 | R$ 50,00       | 1 ano apos a venda |"
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
        "1. Faca upload do arquivo CSV mensal (pode ser feito multiplas vezes)\n"
        "2. O sistema acumula os dados e evita duplicatas por cupom\n"
        "3. Calcula automaticamente os pontos (1%) com validade de 1 ano por venda\n"
        "4. Consulte o dashboard para visualizar metricas\n"
        "5. Use a aba **A Expirar** para antecipar pontos proximos do vencimento\n"
        "6. Acompanhe pontos ja expirados na aba correspondente\n"
        "7. Exporte relatorios quando necessario"
    )

# ============================================
# RODAPE
# ============================================
st.markdown("---")
st.markdown(
    "<div style='text-align: center; color: gray;'>"
    "Sistema de Bonificacao v2.0 | Desenvolvido com Streamlit"
    "</div>",
    unsafe_allow_html=True
)
