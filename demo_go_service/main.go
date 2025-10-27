// MODX_DETERMINISTIC_FALLBACK: aggressive modernization applied
package main

import (
	"fmt"
	"github.com/gorilla/mux"
	"net/http"
)

func main() {
	r := mux.NewRouter()
	r.HandleFunc("/", HomeHandler)
	http.ListenAndServe(":8080", r)
}

func HomeHandler(w http.ResponseWriter, r *http.Request) {
	message := "Hello from legacy Go service"
	version := "1.0"
	fmt.Fprintf(w, message+" version "+version)
}
