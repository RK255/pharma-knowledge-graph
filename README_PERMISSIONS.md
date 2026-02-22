# Neo4j Permission Fix for RxNorm Graph Builder

## Issue
The graph_discovery_v7.py script was encountering permission issues when:
1. Clearing the Neo4j database (Neo4j container running as user 7474)
2. Writing provenance files (host user kage)

## Solution
Created a shared group approach that allows both operations to work:

### Setup Commands
```bash
# Create shared group
sudo groupadd docker_shared

# Add your user to the group
sudo usermod -a -G docker_shared kage

# Set group ownership on data directory
sudo chown -R kage:docker_shared /mnt/fast_raid/server_projects/Geo/graph_workshop/data/
sudo chmod -R 775 /mnt/fast_raid/server_projects/Geo/graph_workshop/data/
sudo chmod -R g+s /mnt/fast_raid/server_projects/Geo/graph_workshop/data/

# Get group ID
GROUP_ID=\$(getent group docker_shared | cut -d: -f3)

# Restart Neo4j with shared group
docker stop neo4j-server
docker rm neo4j-server
docker run -d \
  --name neo4j-server \
  --user "\$(id -u):\$GROUP_ID" \
  --group-add "\$GROUP_ID" \
  -p 7474:7474 -p 7687:7687 \
  -v /mnt/fast_raid/server_projects/Geo/graph_workshop/data:/data \
  -e NEO4J_AUTH=neo4j/BowserNodes \
  -e NEO4J_PLUGINS='["apoc"]' \
  neo4j:4.4
