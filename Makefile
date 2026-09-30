install:
	python -m pip install -r requirements.txt
run-api:
	uvicorn app.api:app --reload
run-ui:
	streamlit run app/ui.py
test:
	pytest -q
