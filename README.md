# ProPPa

*ProPPa* is an interactive tool implementing elicitation, representation, and monitoring of process-centric problem patterns. 
It supports:
- Importing OCELs in different formats including OCEL JSON, OCEL XML, and CSV.
- Discovering OCPNs from OCELs based on the approach (van der Aalst and Berti, 2020) and enhancing them based on the approach (Park, Adams, and van der Aalst, 2022).
    - van der Aalst, W.M.P., Berti, A.: Discovering object-centric Petri nets. Fundam.Informaticae 175(1-4), 1–40 (2020)
    - Park, G., Adams, J.N., van der Aalst, W.M.P.: Opera: Object-centric performance analysis (2022)
- Visualizing OCPNs and their enhancements to support the elicitation of problem patterns.
- Designing pattern graphs using graphical tools.
- Computing behavioral properties of OCELs and evaluating the existence of pattern graphs based on the behavioral properties.
- Visualizing monitoring results with detailed analysis results.


# Demo Video
[![ProPPa DEMO VIDEO](resources/images/demo-video.png)](https://youtu.be/H0TfM76veTc "ProPPa DEMO VIDEO")

# Deployment

### Automatic
For automatic and platform-independent deployment, simply execute the following commands:
```shell script
git clone https://github.com/gyunamister/ProPPa.git
cd src/
docker-compose up
```
After installations, the web service is available at *127.0.0.1/8050*. 
The default username is *admin*, and the default password is *test123* for logging into the system.
If you would like the Dash web service to run in debug mode, then change the value of the environment variable **DEBUG_MODE** in the [env file](src/.env) to **true**.

Example logs (Production and P2P processes) are available at [examples](example-files/).

### Manual

Please make sure to install the binaries of [Graphviz](https://graphviz.org/) and [Python 3.8.8](https://www.python.org/downloads/release/python-383/) before you proceed. In the following, shell scripts are developed for the zsh, so if you use a different shell, then you need to modify the scripts accordingly.

In the first shell:

```bash
git clone https://github.com/gyunamister/ProPPa.git
cd src/backend/db
docker-compose up
```

In the second shell:

```bash
export PROPPA_PATH=<path_to_your_project_root> # the directory where src/ is located
cd src/backend
./run_celery.sh
```

Alternatives to Windows:

```bash
pip install eventlet  
set REDIS_LOCALHOST_OR_DOCKER=localhost
set RABBIT_LOCALHOST_OR_DOCKER=localhost
set RABBITMQ_USER=dtween
set RABBITMQ_PASSWORD=dtween191!
cd src/backend/tasks
celery -A tasks worker --loglevel=INFO -P eventlet
```

In the third shell:

```bash
export PROPPA_PATH=<path_to_your_project_root> # the directory where src/ is located
cd src/backend
./run_opera.sh
```

The default username is admin, and the default password is test123 for logging into the system available at 127.0.0.1/8050.
