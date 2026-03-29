box::use(
  shiny,
  bslib,
  shinyjs,
)

#' @export
ui <- function(id) {
  ns <- shiny$NS(id)

  shiny$tagList(
    # Include custom CSS for the card
    shiny$tags$head(
      shiny$tags$style(
        shiny$HTML("
          .custom-card {
            width: 100%;
            max-width: 45%;
            background-color: white;
            border-radius: 15px;
            box-shadow: 0 10px 20px rgba(0, 0, 0, 0.15);
            margin-bottom: 30px;
            overflow: hidden;
            transition: transform 0.3s, box-shadow 0.3s;
          }

          .custom-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 15px 25px rgba(0, 0, 0, 0.2);
          }

          .custom-card-header {
            background: linear-gradient(135deg, #7F1715, #4A90E2);
            color: white;
            padding: 20px;
            font-size: 1rem;
            font-weight: bold;
            text-align: center;
          }

          .custom-card-body {
            padding: 20px;
            background-color: #ffffff;
          }

          .custom-card-body img {
            width: 100%;
            height: auto;
            border-radius: 10px;
            margin-bottom: 20px;
          }

          .custom-card-body p {
            font-size: 1rem;
            line-height: 1.6;
            color: #333;
            text-align: justify;
          }

          .custom-card-footer {
            padding: 20px;
            text-align: center;
            background-color: #f1f1f1;
          }

          .custom-card-footer .btn-custom {
            background-color: #7F1715;
            color: white;
            padding: 12px 24px;
            font-size: 1rem;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            transition: background-color 0.3s;
          }

          .custom-card-footer .btn-custom:hover {
            background-color: #a0201a;
          }

          @media (max-width: 768px) {
            .custom-card {
              max-width: 100%;
            }
          }
        ")
      )
    ),

    # Main container
    shiny$tags$div(
      style = "display: flex; justify-content: space-around; align-items: flex-start; flex-wrap: wrap; gap: 30px; padding: 30px; background-color: #F8F9FA;",

      # Custom Card 1: Brian Pillmore
      shiny$tags$div(class = "custom-card",
        shiny$tags$div(class = "custom-card-header", "Introducing the Municipal Sales Tax Analysis Tool"),
        shiny$tags$div(class = "custom-card-body",
          shiny$img(src = "static/brian1.png"),
          shiny$tags$p(
            "Developed under the leadership of Mayor Brian Pillmore of Yukon, Oklahoma, our Sales Tax Analysis Tool provides a powerful way to track and forecast sales tax revenues with precision. Originally designed for the City of Yukon, this tool allows any Oklahoma municipality to easily analyze their monthly sales tax receipts from the Oklahoma Tax Commission. By utilizing historical data, municipalities can generate forecasts with 99% confidence, ensuring that future revenues will fall within predicted upper and lower bounds. This tool empowers local governments to make informed financial decisions, plan more effectively, and ensure fiscal stability."
          )
        ),
        shiny$tags$div(class = "custom-card-footer",
        
        shiny$actionButton(
          ns("brian_button"), 
          "Learn more", 
          class = "btn-custom"
        )
        )
      ),

      # Custom Card 2: About Application
      shiny$tags$div(class = "custom-card",
        shiny$tags$div(class = "custom-card-header", "About Application"),
        shiny$tags$div(class = "custom-card-body",
          shiny$tags$p(
            "Please upload the tax data for your city to generate a comprehensive PDF report. The report will include detailed analysis and visualizations of the city's tax revenues. If you need a reference, you can download sample data and an example report using the links below. The sample data will give you an idea of the required format, and the example report will show you what to expect in terms of insights and information. Ensure that your data is formatted correctly before uploading to avoid any issues during the report generation."
          )
        )
      )
      # shiny$tags$div(class = "custom-card",
      #   shiny$tags$div(class = "custom-card-header", "Disclaimer"),
      #   shiny$tags$div(class = "custom-card-body",
      #     shiny$tags$p(
      #       "Disclaimer: This tool is provided as a resource to assist municipalities in analyzing sales tax revenue data. The City of Yukon, Mayor Brian Pillmore, and all associated parties disclaim any liability for decisions made based on the forecasts or data presented by this tool. Users are advised to consult with financial professionals before making any significant fiscal decisions."
      #     )
      #   )
      # )
    )
  )
}

#' @export
server <- function(id) {
  shiny$moduleServer(id, function(input, output, session) {
    shiny$observeEvent(input$brian_button, {
      shinyjs$runjs("window.location.href = 'https://pillmoreforyukon.com/';")
    })
  })
}
