package cmd

import (
	"fmt"
	"io/ioutil"
	"strings"
	"gopkg.in/yaml.v3"
	"github.com/spf13/cobra"
	"github.com/jonasvinther/medusa/pkg/vaultengine"
	"github.com/jonasvinther/medusa/pkg/importer"
	//"github.com/jonasvinther/medusa/pkg/encrypt"
)

func init() {
	rootCmd.AddCommand(copyCmd)
	copyCmd.PersistentFlags().StringP("engine-type", "m", "kv2", "Specify the secret engine type [kv1|kv2]")
}

var copyCmd = &cobra.Command{
	Use:   "copy",
	Short: "Copy Vault secret from one path to another",
	Long:  ``,
	Args:  cobra.MinimumNArgs(2), // Le chemin source, chemin cible, adresse Vault, token
	RunE: func(cmd *cobra.Command, args []string) error {
		sourcePath := args[0]
		targetPath := args[1]
		vaultAddr, _ := cmd.Flags().GetString("address")
		vaultToken, _ := cmd.Flags().GetString("token")
		vaultRole, _ := cmd.Flags().GetString("role")
		kubernetes, _ := cmd.Flags().GetBool("kubernetes")
		authPath, _ := cmd.Flags().GetString("kubernetes-auth-path")
		insecure, _ := cmd.Flags().GetBool("insecure")
		namespace, _ := cmd.Flags().GetString("namespace")
		engineType, _ := cmd.Flags().GetString("engine-type")

		// Créer un client Vault
		client := vaultengine.NewClient(vaultAddr, vaultToken, insecure, namespace, vaultRole, kubernetes, authPath)

		// Splitting the path and determining engine type
		engine, sourcePath, err := client.MountpathSplitPrefix(sourcePath)
		if err != nil {
			fmt.Println("Erreur lors du split du chemin source:", err)
			return err
		}
		client.UseEngine(engine)
		client.SetEngineType(engineType)

		// Exporter le secret du chemin source
		exportData, err := client.FolderExport(sourcePath)
		if err != nil {
			fmt.Println("Erreur lors de l'export:", err)
			return err
		}

		// Si les données sont vides, lève une exception
		if len(exportData) == 0 {
			return fmt.Errorf("Aucune donnée trouvée dans le chemin source %s", sourcePath)
		}

		// Exporter les données dans un fichier temporaire (format YAML)
		tempFileName := "/tmp/exported_secret.yaml"
		data, err := vaultengine.ConvertToYaml(exportData)
		if err != nil {
			fmt.Println("Erreur lors de la conversion en YAML:", err)
			return err
		}

		err = ioutil.WriteFile(tempFileName, data, 0644)
		if err != nil {
			fmt.Println("Erreur lors de l'écriture du fichier:", err)
			return err
		}
 
		// Appel de la fonction extractYamlData pour modifier le fichier YAML
		// Passer le chemin du fichier exporté et le chemin à extraire (par exemple, sourcePath)
		sourcePath = strings.TrimSuffix(sourcePath, "/")
		fmt.Println(sourcePath)
		err = extractYamlData(tempFileName, sourcePath)
		if err != nil {
			fmt.Println("Erreur lors de l'extraction des données YAML:", err)
			return err
		}

		// Lire le fichier modifié
		fileData, err := ioutil.ReadFile(tempFileName)
		if err != nil {
			fmt.Println("Erreur lors de la lecture du fichier exporté:", err)
			return err
		}

		// Importer les données modifiées
		parsedYaml, err := importer.Import(fileData)
		if err != nil {
			fmt.Println("Erreur lors de l'importation des données YAML:", err)
			return err
		}

		// Écrire les données dans le chemin cible dans Vault
		for subPath, value := range parsedYaml {
			fullPath := targetPath + subPath
			fmt.Println(fullPath)			
			client.SecretWrite(fullPath, value)
		}

		// Supprimer le fichier temporaire après l'import
		// err = os.Remove(tempFileName)
		// if err != nil {
		// 	fmt.Println("Erreur lors de la suppression du fichier temporaire:", err)
		// 	return err
		// }

		// Retourner un message de succès
		fmt.Printf("Le secret du chemin %s a été copié avec succès vers %s\n", sourcePath, targetPath)
		return nil
	},
}

func extractYamlData(inputFile, path string) error {
	// Charger le fichier YAML
	fileContent, err := ioutil.ReadFile(inputFile)
	if err != nil {
		return fmt.Errorf("erreur lors de la lecture du fichier: %v", err)
	}

	var data map[string]interface{}
	// Parse le fichier YAML dans une structure de données Go
	if err := yaml.Unmarshal(fileContent, &data); err != nil {
		return fmt.Errorf("erreur lors du parsing du fichier YAML: %v", err)
	}

	// Convertir le path en liste de clés
	pathKeys := strings.Split(path, "/")

	// Accéder aux données correspondant au path
	for _, key := range pathKeys {
		if value, exists := data[key]; exists {
			// Si la clé existe, on met à jour 'data' avec la valeur associée
			// On vérifie si la valeur est un map et si c'est le dernier niveau
			if mapData, ok := value.(map[string]interface{}); ok {
				data = mapData
			} else {
				// Si ce n'est pas un map, on assigne directement la valeur
				data = map[string]interface{}{key: value}
				break
			}
		} else {
			return fmt.Errorf("le chemin '%s' n'existe pas dans le fichier YAML", path)
		}
	}

	// Sauvegarder les données extraites dans un nouveau fichier YAML
	outputFile := "/tmp/exported_secret.yaml"
	outputData, err := yaml.Marshal(data)
	if err != nil {
		return fmt.Errorf("erreur lors de la conversion des données en YAML: %v", err)
	}

	if err := ioutil.WriteFile(outputFile, outputData, 0644); err != nil {
		return fmt.Errorf("erreur lors de l'écriture du fichier de sortie: %v", err)
	}

	fmt.Printf("Les données extraites ont été enregistrées dans '%s'.\n", outputFile)
	return nil
}
