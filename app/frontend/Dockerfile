# Use a lightweight Nginx image to serve static content
FROM nginx:alpine

# Copy the HTML file into the default Nginx public directory
COPY ./index.html /usr/share/nginx/html/

# Expose port 80
EXPOSE 80