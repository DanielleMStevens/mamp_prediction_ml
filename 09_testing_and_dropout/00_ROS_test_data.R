# Load the ggplot2 library
library(ggplot2)
library(readxl)
library(reshape2)

# Read the Excel file from the same directory
data <- as.data.frame(readxl::read_xlsx(path = "./09_testing_and_dropout/ROS_screen_plots/Summary_csp22_validation_data.xlsx"))
save_sol_name <- data[1,]
data <- data[-1,]
data <- reshape2::melt(data, id.vars = c("Sol Number"))
colnames(data) <- c("Epitope", "Sol_Number", "value")
data$value <- as.numeric(data$value)

# 1. Handle negative values for size: Replace values < 0 with 1
# We create a new column for size to keep the original 'value' for coloring
data$size_mapped <- ifelse(data$value < 0, 1, data$value)

# Define the colors
data$color_category <- cut(data$value, breaks = c(-Inf, 14999, 75000, Inf), labels = c("0-14,999", "15,000-74,999", ">75,000"), right = TRUE)
color_mapping <- c("0-14,999" = "#8B0000", "15,000-74,999" = "#00008B", ">75,000" = "#4A4A4A")

# --- Create the Bubble Plot ---
bubble_plot <- ggplot(data, aes(x = Sol_Number, y = Epitope)) +
  geom_point(aes(size = size_mapped, fill = color_category), shape = 21, color = "black", alpha = 0.6) +
  scale_size_continuous(range = c(0.05, 8), guide = "none") +
  scale_fill_manual(values = color_mapping,name = "Avg. Max. RLUs") +
  ylab("Epitope") +
  xlab("Species") +
  theme_classic() +
  coord_flip() +
  theme(legend.position = "right", 
    axis.text.x = element_text(angle = 90, hjust = 1, size = 8, color = "black"),
    axis.text.y = element_text(size = 8, color = "black"),
    axis.title.x = element_text(size = 10, color = "black"),
    axis.title.y = element_text(size = 10, color = "black"),
    panel.border = element_rect(color = "black", fill = NA),
    panel.grid.minor = element_line(color = "grey90", size = 0.2),
    panel.grid.major = element_line(color = "grey90", size = 0.2))


# If you want to save the plot:
ggsave("./09_testing_and_dropout/ROS_screen_plots/ROS_bubble_plot.pdf", plot = bubble_plot, width = 10, height = 2.2, dpi = 300)


# Create summary plot of immunogenic outcomes grouped by Sol_Number
summary_plot <- ggplot(data[!is.na(data$value),], aes(x = Sol_Number, fill = factor(color_category, 
        levels = c(">75,000", "15,000-74,999", "0-14,999")))) +
  geom_bar(position = "dodge", color = "black", alpha = 0.6, linewidth = 0.3) +
  scale_fill_manual(values = color_mapping, name = "RLU Category") +
  ylim(0, 36) +
  theme_classic() +
  theme(
    axis.text.x = element_text(angle = 45, hjust = 1, size = 8, color = "black"),
    axis.text.y = element_text(size = 8, color = "black"), 
    axis.title.x = element_text(size = 9, color = "black"),
    axis.title.y = element_text(size = 9, color = "black"),
    legend.position = "none",
    panel.border = element_rect(color = "black", fill = NA),
    panel.grid.minor = element_line(color = "grey90", size = 0.2),
    panel.grid.major = element_line(color = "grey90", size = 0.2)
  ) +
  labs(x = "Species", y = "Count") +
  geom_text(stat = 'count', 
            aes(label = after_stat(count)), 
            position = position_dodge(width = 0.9),
            vjust = -0.5,
            size = 2.5)

# Save the summary plot
ggsave("./09_testing_and_dropout/ROS_screen_plots/ROS_summary_plot.pdf", plot = summary_plot, width = 1.9, height = 2.2, dpi = 300)
