import azure.functions as func

from activities.fetch_restaurant_menu import bp as fetch_restaurant_menu_bp
from activities.generate_recreation import bp as generate_recreation_bp
from activities.geocode_restaurant_candidates import bp as geocode_restaurant_candidates_bp
from activities.match_menu_item import bp as match_menu_item_bp
from activities.persist_job_result import bp as persist_job_result_bp
from activities.query_culinary_embeddings import bp as query_culinary_embeddings_bp
from activities.vision_guess import bp as vision_guess_bp
from orchestrators.dish_orchestrator import bp as dish_orchestrator_bp
from triggers.job_result_http import bp as job_result_http_bp
from triggers.job_save_http import bp as job_save_http_bp
from triggers.jobs_list_http import bp as jobs_list_http_bp
from triggers.orchestrator_starter_queue import bp as orchestrator_starter_queue_bp
from triggers.upload_http import bp as upload_http_bp

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)


@app.route(route="ping", methods=["GET"])
def ping(req: func.HttpRequest) -> func.HttpResponse:
    return func.HttpResponse("pong", status_code=200)


app.register_blueprint(vision_guess_bp)
app.register_blueprint(geocode_restaurant_candidates_bp)
app.register_blueprint(fetch_restaurant_menu_bp)
app.register_blueprint(match_menu_item_bp)
app.register_blueprint(query_culinary_embeddings_bp)
app.register_blueprint(generate_recreation_bp)
app.register_blueprint(persist_job_result_bp)

app.register_blueprint(dish_orchestrator_bp)

app.register_blueprint(upload_http_bp)
app.register_blueprint(orchestrator_starter_queue_bp)
app.register_blueprint(job_result_http_bp)
app.register_blueprint(jobs_list_http_bp)
app.register_blueprint(job_save_http_bp)
