# Prediction Markets Research Assistant

A multi-agent AI system for live prediction market intelligence across Kalshi and Polymarket.

## Overview
This application uses a 3-agent pipeline to:
1. **Collect**: Fetch live top markets by volume from Kalshi and Polymarket.
2. **Classify**: Group markets into sectors (Sports, Politics, Finance, Crypto, World) and identify matched pairs across platforms.
3. **Strategize**: Generate academic-grounded sector verdicts and specific trade recommendations based on cross-exchange spreads and efficiency theory (Wolfers & Zitzewitz 2006).

## Tech Stack
- **Framework**: Streamlit
- **Intelligence**: OpenAI GPT-4o-mini
- **Database**: SQLite (RAG Knowledge Base)
- **Data Integration**: Kalshi API V2, Polymarket Gamma API

## Getting Started

1.  **Environment Setup**:
    ```bash
    python -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    ```

2.  **Configuration**:
    Create a `.env` file with your API keys:
    ```
    OPENAI_API_KEY=your_key_here
    KALSHI_API_KEY=your_key_here
    ```

3.  **Initialize Knowledge Base**:
    ```bash
    python build_kb.py
    ```

4.  **Run the App**:
    ```bash
    streamlit run app.py
    ```

## References
- Wolfers, J., & Zitzewitz, E. (2006). "Prediction Markets in Theory and Practice." NBER Working Paper 12083.
