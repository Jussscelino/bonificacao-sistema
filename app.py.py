
**Aceita variações:**
- Valores com vírgula decimal: `1500,00`
- Valores com R$: `R$ 1.500,00`
- Datas em vários formatos: `2025-01-15`, `15/01/2025`, `15-01-2025`

### Fluxo de Uso
1. Faça upload do arquivo CSV mensal
2. O sistema calcula automaticamente os pontos (1%)
3. Consulte o dashboard para visualizar métricas
4. Acompanhe a validade dos pontos na aba de clientes
5. Exporte relatórios quando necessário
""")

# ============================================
# RODAPÉ
# ============================================
st.markdown("---")
st.markdown(
"<div style='text-align: center; color: gray;'>"
"Sistema de Bonificação v1.1 | Desenvolvido com Streamlit"
"</div>",
unsafe_allow_html=True
)
