{ port, ... }: {
  config = {

    services.postgres = {
      service = {
        image = "postgres:12";
        restart = "always";
        volumes = [ "dbdata:/var/lib/postgresql/data" ];
        env_file = [ "/run/secrets/nextcloud/environment" ];
      };
    };

    services.nextcloud = {
      service = {
        image = "nextcloud";
        restart = "always";
        volumes = [ "nextclouddata:/var/www/html" ];
        env_file = [ "/run/secrets/nextcloud/environment" ];
        ports = [
          "${toString port}:80"
        ];
        environment = {
          POSTGRES_HOST = "postgres";
        };
        depends_on = [ "postgres" ];
      };
    };

    docker-compose.raw = {
      volumes = {
        dbdata = null;
        nextclouddata = null;
      };
    };
  };
}
