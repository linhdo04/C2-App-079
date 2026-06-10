export type TelemetryReading = {
  timestamp: string;
  temperature_celsius: number | null;
  humidity_percent: number | null;
  node_name: string;
  mission_name: string;
};

export type TelemetryResponse = {
  data: TelemetryReading[];
  meta: {
    count: number;
    limit: number;
    latest_timestamp: string | null;
  };
};
